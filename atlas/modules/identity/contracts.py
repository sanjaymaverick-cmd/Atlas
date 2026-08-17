"""Identity's published interface.

Blueprint §22: other modules integrate against this, not against
``identity.*`` tables. ``.importlinter`` enforces it — an import of
``identity.models`` or ``identity.repository`` from outside this package fails
CI.

The shape here is deliberately narrow. ``check_scoped_role`` returns a boolean
rather than a role list, so callers cannot re-derive the scoping rule and drift
from it. That rule — a role may be global, or bound to a legal entity, or to a
project — is the mechanism behind §2's legal-entity separation and project
isolation, and it exists in exactly one place.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.schemas import DeviceSummary, SessionContext, UserSummary


class IdentityContract(Protocol):
    """What Organization, Audit and the owner console may call."""

    async def get_user(self, session: AsyncSession, user_id: UUID) -> UserSummary | None:
        """Return non-sensitive user details, or ``None`` if unknown."""
        ...

    async def get_session(self, session: AsyncSession, session_id: UUID) -> SessionContext | None:
        """Return the facts needed to authorise a request on this session.

        Returns ``None`` for an unknown session. A revoked or expired session
        is returned rather than hidden, so the access check can give an
        accurate refusal reason to the audit trail.
        """
        ...

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        """Whether the user holds a role granting ``permission_code`` here.

        A role with a null ``legal_entity_id`` and null ``project_id`` is
        global and grants everywhere. A role bound to a legal entity grants
        within that entity, including its projects. A role bound to a project
        grants only there.

        Scoping is a narrowing, never a widening: a role scoped to entity A
        cannot reach entity B, and asking about a wider scope than the role
        covers returns ``False``.
        """
        ...

    async def list_pending_devices(self, session: AsyncSession) -> list[DeviceSummary]:
        """Devices awaiting owner approval, for the owner console queue."""
        ...

    async def authenticate_session_token(
        self, session: AsyncSession, token: str
    ) -> SessionContext | None:
        """Resolve an opaque bearer token to an active session.

        The token is hashed inside Identity before lookup. Callers never see
        the stored hash or Identity's session rows.
        """
        ...
