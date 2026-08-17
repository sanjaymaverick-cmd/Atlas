"""Step-up authentication policy.

Blueprint §15 lists the actions that require stronger approval than an ordinary
authenticated session. Step-up is re-authentication against the user's
passkey immediately before such an action.

The freshness window is the point of this module. ``identity.sessions`` carries
a ``step_up_verified`` boolean, and a boolean alone never decays: one step-up
performed to approve a contract would silently authorise a payment release an
hour later. So a step-up is treated as valid only for a short window after it
was performed, recorded in ``step_up_verified_at`` — see
``docs/schema-findings-phase1.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum


class SensitiveAction(StrEnum):
    """Actions requiring step-up authentication.

    The first ten are Blueprint §15's list verbatim. ``BREAK_GLASS_INVOKE`` is
    added here: the blueprint does not name it, but invoking the break-glass
    credential grants owner-level authority (§3.2) and is structurally the most
    sensitive action in the system, so exempting it would be indefensible.
    """

    CONTRACT_APPROVAL = "contract.approve"
    PAYMENT_APPROVAL = "payment.approve"
    BANK_DETAIL_CHANGE = "party.bank_details.change"
    VENDOR_MASTER_CHANGE = "vendor.master.change"
    CUSTOMER_PRICE_OVERRIDE = "customer.price.override"
    DOCUMENT_DOWNLOAD = "document.download"
    USER_ROLE_MODIFICATION = "user.role.modify"
    DEVICE_ENROLLMENT = "device.enroll"
    AUDIT_EXPORT = "audit.export"
    BACKUP_RESTORATION = "backup.restore"
    BREAK_GLASS_INVOKE = "break_glass.invoke"


DEFAULT_STEP_UP_TTL = timedelta(minutes=5)
"""How long a step-up remains valid.

Short enough that it authorises the action the user just re-authenticated for
and not a later one they did not have in mind. Five minutes accommodates a
slow passkey ceremony and a form submission without leaving a usable window
open on an unattended screen.
"""


class StepUpRequiredError(Exception):
    """Raised when an action needs a step-up the session does not currently hold."""

    def __init__(self, action: SensitiveAction, reason: str) -> None:
        super().__init__(f"step-up required for {action.value}: {reason}")
        self.action = action
        self.reason = reason


def requires_step_up(action: str) -> bool:
    """Whether ``action`` is on the sensitive list.

    Unknown actions return ``False``. This is a deliberate default: the list is
    an escalation list, not an authorisation list, and ordinary permission
    checks (``atlas.platform.access_control``) still gate every action
    regardless. Failing closed here would block every ordinary read.
    """
    return action in set(SensitiveAction)


def is_step_up_fresh(
    *,
    step_up_verified: bool,
    step_up_verified_at: datetime | None,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_STEP_UP_TTL,
) -> bool:
    """Whether a session currently holds a valid step-up.

    Args:
        step_up_verified: The session's flag.
        step_up_verified_at: When step-up was last performed.
        now: Current time; injectable for testing. Must be timezone-aware.
        ttl: Freshness window.

    Returns:
        ``True`` only if the flag is set, a timestamp exists, and that timestamp
        is within ``ttl`` of ``now``.

    A set flag with no timestamp returns ``False``. Such a row predates the
    freshness column and cannot be shown to be recent, so it is treated as
    stale rather than trusted.
    """
    if not step_up_verified or step_up_verified_at is None:
        return False

    moment = now if now is not None else datetime.now(UTC)
    if step_up_verified_at.tzinfo is None:
        raise ValueError("step_up_verified_at must be timezone-aware")

    age = moment - step_up_verified_at
    # A timestamp in the future means a clock problem or a forged row; either
    # way it is not evidence of a recent ceremony.
    if age < timedelta(0):
        return False
    return age <= ttl


def assert_step_up(
    *,
    action: str,
    step_up_verified: bool,
    step_up_verified_at: datetime | None,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_STEP_UP_TTL,
) -> None:
    """Enforce the step-up requirement for ``action``.

    Does nothing when the action is not sensitive, or when it is and the
    session holds a fresh step-up.

    Raises:
        StepUpRequiredError: When a sensitive action lacks a fresh step-up.
    """
    if not requires_step_up(action):
        return

    sensitive = SensitiveAction(action)
    if not step_up_verified:
        raise StepUpRequiredError(sensitive, "session has not completed step-up")
    if step_up_verified_at is None:
        raise StepUpRequiredError(sensitive, "step-up has no recorded timestamp")
    if not is_step_up_fresh(
        step_up_verified=step_up_verified,
        step_up_verified_at=step_up_verified_at,
        now=now,
        ttl=ttl,
    ):
        raise StepUpRequiredError(sensitive, "step-up has expired")
