"""Break-glass credential state machine.

Blueprint §3.2: a sealed, physically-secured credential held by a second
trusted party, invoked only when the primary owner is unreachable, auditable on
use. It closes the audit's finding that a single administrator with no backup
is itself a single point of failure.

Two things are enforced here rather than in the database.

First, transition order. ``identity.break_glass_credentials.status`` carries
``CHECK (status IN ('sealed','invoked','revoked'))`` — a value list, not a state
machine. Nothing in that constraint prevents ``invoked -> sealed``, i.e.
silently re-sealing a one-shot emergency credential after use, which would
destroy the "used exactly once, and it shows" property the mechanism depends
on. Re-arming after use means issuing a *new* credential against a newly
sealed physical reference, never resetting the old row.

Second, the grant is time-boxed and never touches ``users.is_owner``.
Promoting the holder to a permanent owner would leave the escalation in place
long after the emergency, and would be invisible in the users table as anything
other than a second owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID


class BreakGlassStatus(StrEnum):
    """Mirrors the CHECK constraint on ``break_glass_credentials.status``."""

    SEALED = "sealed"
    INVOKED = "invoked"
    REVOKED = "revoked"


# Legal transitions. Note the absence of any edge back to SEALED.
_ALLOWED: dict[BreakGlassStatus, frozenset[BreakGlassStatus]] = {
    BreakGlassStatus.SEALED: frozenset({BreakGlassStatus.INVOKED, BreakGlassStatus.REVOKED}),
    BreakGlassStatus.INVOKED: frozenset({BreakGlassStatus.REVOKED}),
    BreakGlassStatus.REVOKED: frozenset(),
}

DEFAULT_GRANT_TTL = timedelta(hours=4)
"""How long break-glass authority lasts before it lapses on its own.

Matched to the blueprint's recommended 4-hour RTO (§3.2): long enough to carry
out the recovery the credential exists for, short enough that an unrevoked
invocation does not become a standing second owner. The owner can revoke
sooner, and should.
"""


class BreakGlassError(Exception):
    """Base class for break-glass refusals."""


class InvalidTransitionError(BreakGlassError):
    """Raised on an illegal status transition."""

    def __init__(self, current: BreakGlassStatus, requested: BreakGlassStatus) -> None:
        detail = ""
        if requested is BreakGlassStatus.SEALED and current is not BreakGlassStatus.SEALED:
            detail = (
                " A used credential cannot be re-sealed; issue a new credential "
                "against a newly sealed physical reference instead."
            )
        super().__init__(
            f"cannot move break-glass credential from {current} to {requested}.{detail}"
        )
        self.current = current
        self.requested = requested


class NotTheHolderError(BreakGlassError):
    """Raised when someone other than the designated holder attempts invocation."""


@dataclass(frozen=True, slots=True)
class BreakGlassGrant:
    """The time-boxed authority produced by a successful invocation.

    Carries no owner flag: authority is this object's existence plus its expiry,
    checked at each request, not a mutation of the holder's user record.
    """

    credential_id: UUID
    holder_user_id: UUID
    reason: str
    granted_at: datetime
    expires_at: datetime

    def is_active(self, now: datetime | None = None) -> bool:
        moment = now if now is not None else datetime.now(UTC)
        return self.granted_at <= moment < self.expires_at


def can_transition(current: BreakGlassStatus, requested: BreakGlassStatus) -> bool:
    """Whether ``current -> requested`` is legal."""
    return requested in _ALLOWED[current]


def assert_transition(current: BreakGlassStatus, requested: BreakGlassStatus) -> None:
    """Raise ``InvalidTransitionError`` unless ``current -> requested`` is legal."""
    if not can_transition(current, requested):
        raise InvalidTransitionError(current, requested)


def invoke(
    *,
    credential_id: UUID,
    holder_user_id: UUID,
    invoking_user_id: UUID,
    current_status: BreakGlassStatus,
    reason: str,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_GRANT_TTL,
) -> BreakGlassGrant:
    """Invoke a sealed break-glass credential.

    The caller is responsible for two things this function cannot check: that
    ``invoking_user_id`` has authenticated with their own passkey, and that a
    fresh step-up was completed (``SensitiveAction.BREAK_GLASS_INVOKE``). This
    function enforces holder identity, transition legality and the reason
    requirement, and computes the grant window.

    Args:
        credential_id: The credential being invoked.
        holder_user_id: Who the credential is registered to.
        invoking_user_id: Who is attempting the invocation.
        current_status: The credential's status as stored.
        reason: Why the credential is being invoked. Required and recorded in
            the audit event; an emergency escalation with no stated cause is
            not auditable after the fact.
        now: Current time; injectable for testing.
        ttl: Grant lifetime.

    Raises:
        NotTheHolderError: If the invoker is not the registered holder.
        InvalidTransitionError: If the credential is not sealed.
        ValueError: If no reason is given.
    """
    if invoking_user_id != holder_user_id:
        raise NotTheHolderError(
            f"user {invoking_user_id} is not the holder of break-glass credential {credential_id}"
        )

    if not reason or not reason.strip():
        raise ValueError("a reason is required to invoke a break-glass credential")

    assert_transition(current_status, BreakGlassStatus.INVOKED)

    granted_at = now if now is not None else datetime.now(UTC)
    return BreakGlassGrant(
        credential_id=credential_id,
        holder_user_id=holder_user_id,
        reason=reason.strip(),
        granted_at=granted_at,
        expires_at=granted_at + ttl,
    )


def revoke(current_status: BreakGlassStatus) -> BreakGlassStatus:
    """Revoke a credential, whether it was sealed or already invoked.

    Revocation must terminate any active grant immediately; containment has to
    be at least as fast as invocation. Callers are responsible for killing the
    holder's break-glass-derived sessions in the same transaction.
    """
    assert_transition(current_status, BreakGlassStatus.REVOKED)
    return BreakGlassStatus.REVOKED
