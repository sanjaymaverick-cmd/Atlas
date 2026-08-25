"""Request authorisation.

Blueprint §15: "Every request is still checked against: user, role, legal
entity, project, module, object classification, action, device trust, session
risk."

This module is that check, as one function with an explicit refusal reason.
Authorisation spread across call sites is authorisation nobody can audit, and
§2's legal-entity separation and project isolation are only as good as the
single place that enforces them.

Ordering matters. Checks run cheapest-and-most-fundamental first — is the user
active, is the session live, is the device trusted — before the scoped-role
lookup, so a revoked device is refused without a role query.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from atlas.platform.step_up import (
    DEFAULT_STEP_UP_TTL,
    is_step_up_fresh,
    requires_step_up,
)


class Classification(StrEnum):
    """Object classification, mirroring ``documents.documents.classification``."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DeviceTrust(StrEnum):
    """Mirrors ``identity.devices.trust_level``."""

    STANDARD = "standard"
    ELEVATED = "elevated"


# Classifications that may only be reached from a device the owner has raised to
# elevated trust. Blueprint §15 makes device trust a first-class dimension; the
# concrete rule is that the most sensitive material is not reachable from an
# ordinary enrolled laptop.
_REQUIRES_ELEVATED_DEVICE = frozenset({Classification.RESTRICTED})

DEFAULT_MAX_SESSION_RISK = 50.0
"""Risk score above which a session is refused outright.

``identity.sessions.risk_score`` is NUMERIC(5,2), scored elsewhere. The
threshold lives here so it is applied uniformly rather than per call site.
"""


class AccessDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class AccessRequest:
    """Everything the §15 check needs about one request."""

    user_id: UUID
    user_status: str
    session_active: bool
    session_expires_at: datetime
    session_risk_score: float
    step_up_verified: bool
    step_up_verified_at: datetime | None
    device_status: str
    device_trust: DeviceTrust
    module: str
    action: str
    classification: Classification
    legal_entity_id: UUID | None
    project_id: UUID | None


@dataclass(frozen=True, slots=True)
class AccessResult:
    decision: AccessDecision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is AccessDecision.ALLOW


def _deny(reason: str) -> AccessResult:
    return AccessResult(AccessDecision.DENY, reason)


_ALLOWED = AccessResult(AccessDecision.ALLOW, "all checks passed")


def check_access(
    request: AccessRequest,
    *,
    has_scoped_role: bool,
    now: datetime | None = None,
    max_session_risk: float = DEFAULT_MAX_SESSION_RISK,
    step_up_ttl: timedelta = DEFAULT_STEP_UP_TTL,
) -> AccessResult:
    """Decide whether a request may proceed.

    Args:
        request: The request context.
        has_scoped_role: Whether the user holds a role granting ``action`` in
            this legal entity and project. Supplied by the Identity module via
            its contract — this function never queries ``identity.user_roles``
            itself, so the scoping rule stays in one place.
        now: Current time; injectable for testing.
        max_session_risk: Risk score above which the session is refused.
        step_up_ttl: Freshness window for step-up.

    Returns:
        An ``AccessResult`` carrying an explicit reason on refusal. Reasons are
        for the audit trail; what is shown to the user should be less specific,
        since a precise refusal reason is itself information.
    """
    moment = now if now is not None else datetime.now(UTC)

    # 1. User
    if request.user_status != "active":
        return _deny(f"user status is {request.user_status!r}")

    # 2. Session
    if not request.session_active:
        return _deny("session is revoked")
    if request.session_expires_at <= moment:
        return _deny("session has expired")
    if request.session_risk_score > max_session_risk:
        return _deny(
            f"session risk score {request.session_risk_score} exceeds threshold {max_session_risk}"
        )

    # 3. Device. A device awaiting owner approval can authenticate nobody —
    #    Blueprint §15 makes enrollment owner-approved, so 'pending_approval'
    #    must not be usable in the interim.
    if request.device_status != "active":
        return _deny(f"device status is {request.device_status!r}")

    # 4. Classification vs device trust
    if (
        request.classification in _REQUIRES_ELEVATED_DEVICE
        and request.device_trust is not DeviceTrust.ELEVATED
    ):
        return _deny(f"{request.classification} objects require an elevated-trust device")

    # 5. Scoped role: role x legal entity x project
    if not has_scoped_role:
        return _deny(
            f"no role granting {request.action!r} in "
            f"legal_entity={request.legal_entity_id} project={request.project_id}"
        )

    # 6. Step-up for sensitive actions. Last because it is the only check whose
    #    remedy is an action the user can take right now.
    if requires_step_up(request.action) and not is_step_up_fresh(
        step_up_verified=request.step_up_verified,
        step_up_verified_at=request.step_up_verified_at,
        now=moment,
        ttl=step_up_ttl,
    ):
        return _deny(f"{request.action!r} requires a fresh step-up authentication")

    return _ALLOWED
