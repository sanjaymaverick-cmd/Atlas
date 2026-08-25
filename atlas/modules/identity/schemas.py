"""Identity DTOs — part of the module's published surface.

These cross the module boundary; the ORM models behind them do not. Nothing
here carries credential material: no public keys, no credential ids, no session
token hashes. A caller that needs to know whether a user may do something asks
``check_scoped_role``; it never receives the material that would let it decide
for itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from atlas.platform.access_control import DeviceTrust


@dataclass(frozen=True, slots=True)
class CeremonyOptions:
    ceremony_id: UUID
    public_key: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuthenticationOutcome:
    session_token: str | None
    expires_at: datetime | None
    clone_detected: bool = False


@dataclass(frozen=True, slots=True)
class RelyingParty:
    """Stable WebAuthn relying-party identity and allowed browser origin."""

    rp_id: str
    rp_name: str
    origin: str


@dataclass(frozen=True, slots=True)
class UserSummary:
    """Non-sensitive user identification."""

    id: UUID
    full_name: str
    email: str
    is_owner: bool
    status: str

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Everything the access check needs about a live session.

    Deliberately carries no token or token hash. Callers receive the facts
    needed to authorise a request, not the material needed to impersonate it.
    """

    session_id: UUID
    user_id: UUID
    device_id: UUID
    user_status: str
    device_status: str
    device_trust: DeviceTrust
    risk_score: float
    step_up_verified: bool
    step_up_verified_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    """A registered device, as shown in the owner's approval queue."""

    id: UUID
    user_id: UUID
    device_name: str | None
    trust_level: DeviceTrust
    status: str
    enrolled_at: datetime
    last_used_at: datetime | None
