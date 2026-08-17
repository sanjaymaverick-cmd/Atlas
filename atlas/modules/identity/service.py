"""Identity service — the concrete ``IdentityContract``.

Owns authentication, devices, sessions, scoped roles and the break-glass
credential. Everything other modules are allowed to ask is here; everything
they are not allowed to ask is in ``repository.py`` and ``models.py``, which
they cannot import.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity import repository as repo
from atlas.modules.identity.break_glass import (
    BreakGlassGrant,
    BreakGlassStatus,
)
from atlas.modules.identity.break_glass import (
    invoke as invoke_break_glass,
)
from atlas.modules.identity.break_glass import (
    revoke as revoke_break_glass,
)
from atlas.modules.identity.models import BreakGlassCredential, Device
from atlas.modules.identity.schemas import DeviceSummary, SessionContext, UserSummary
from atlas.modules.identity.scoping import any_grant_covers
from atlas.platform.access_control import DeviceTrust
from atlas.platform.audit.writer import record_event


class IdentityError(Exception):
    """Base class for Identity refusals."""


class UnknownDeviceError(IdentityError):
    pass


class NotOwnerError(IdentityError):
    """Raised when a non-owner attempts an owner-only action."""


class IdentityService:
    """Implements ``IdentityContract``."""

    # -- contract ---------------------------------------------------------

    async def get_user(self, session: AsyncSession, user_id: UUID) -> UserSummary | None:
        user = await repo.get_user(session, user_id)
        if user is None:
            return None
        return UserSummary(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            is_owner=user.is_owner,
            status=user.status,
        )

    async def get_session(self, session: AsyncSession, session_id: UUID) -> SessionContext | None:
        found = await repo.get_session_with_context(session, session_id)
        if found is None:
            return None
        row, user, device = found
        return SessionContext(
            session_id=row.id,
            user_id=row.user_id,
            device_id=row.device_id,
            user_status=user.status,
            device_status=device.status,
            device_trust=DeviceTrust(device.trust_level),
            risk_score=float(row.risk_score or 0),
            step_up_verified=row.step_up_verified,
            step_up_verified_at=row.step_up_verified_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        grants = await repo.load_grants(session, user_id)
        if not grants:
            return False

        # An entity-scoped grant can only be shown to cover a project if we know
        # which entity that project belongs to. Looked up only when it can
        # actually change the answer.
        project_entity_id = None
        if project_id is not None:
            project_entity_id = await repo.get_project_entity_id(session, project_id)

        return any_grant_covers(
            grants,
            permission_code=permission_code,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
            project_entity_id=project_entity_id,
        )

    async def list_pending_devices(self, session: AsyncSession) -> list[DeviceSummary]:
        devices = await repo.list_devices_by_status(session, "pending_approval")
        return [
            DeviceSummary(
                id=d.id,
                user_id=d.user_id,
                device_name=d.device_name,
                trust_level=DeviceTrust(d.trust_level),
                status=d.status,
                enrolled_at=d.enrolled_at,
                last_used_at=d.last_used_at,
            )
            for d in devices
        ]

    # -- device enrollment ------------------------------------------------

    async def approve_device(
        self,
        session: AsyncSession,
        *,
        approver_user_id: UUID,
        device_id: UUID,
    ) -> DeviceSummary:
        """Approve an enrolled device. Blueprint §15: owner-approved enrollment.

        The caller must have satisfied ``SensitiveAction.DEVICE_ENROLLMENT``
        step-up before reaching here; this method enforces owner status and
        records the approval.
        """
        approver = await repo.get_user(session, approver_user_id)
        if approver is None or not approver.is_owner:
            raise NotOwnerError(
                f"user {approver_user_id} is not the owner and may not approve devices"
            )

        device = await repo.get_device(session, device_id)
        if device is None:
            raise UnknownDeviceError(f"device {device_id} does not exist")

        before = {"status": device.status, "enrolled_by": str(device.enrolled_by)}
        device.status = "active"
        device.enrolled_by = approver_user_id
        await session.flush()

        await record_event(
            session,
            actor_user_id=approver_user_id,
            entity_schema="identity",
            entity_table="devices",
            entity_id=device.id,
            action="approve",
            before_state=before,
            after_state={"status": device.status, "enrolled_by": str(approver_user_id)},
        )
        return DeviceSummary(
            id=device.id,
            user_id=device.user_id,
            device_name=device.device_name,
            trust_level=DeviceTrust(device.trust_level),
            status=device.status,
            enrolled_at=device.enrolled_at,
            last_used_at=device.last_used_at,
        )

    async def revoke_device(
        self, session: AsyncSession, *, actor_user_id: UUID, device_id: UUID
    ) -> None:
        device = await repo.get_device(session, device_id)
        if device is None:
            raise UnknownDeviceError(f"device {device_id} does not exist")

        before = {"status": device.status}
        device.status = "revoked"
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="identity",
            entity_table="devices",
            entity_id=device.id,
            action="revoke",
            before_state=before,
            after_state={"status": "revoked"},
        )

    async def flag_cloned_device(
        self, session: AsyncSession, *, device_id: UUID, stored: int, presented: int
    ) -> None:
        """Revoke a device whose signature counter failed to advance.

        A stalled counter is the WebAuthn specification's clone signal, so this
        is handled as a security incident rather than a failed login: the
        credential is revoked immediately and the event recorded with both
        counter values, so an operator can see why.
        """
        device = await repo.get_device(session, device_id)
        if device is None:
            raise UnknownDeviceError(f"device {device_id} does not exist")

        device.status = "revoked"
        await session.flush()
        await record_event(
            session,
            actor_user_id=None,  # detected by the system, not performed by a user
            entity_schema="identity",
            entity_table="devices",
            entity_id=device.id,
            action="revoke_suspected_clone",
            after_state={
                "status": "revoked",
                "stored_sign_counter": stored,
                "presented_sign_counter": presented,
            },
        )

    # -- break glass ------------------------------------------------------

    async def seal_break_glass(
        self,
        session: AsyncSession,
        *,
        owner_user_id: UUID,
        holder_user_id: UUID,
        sealed_reference: str,
        purpose: str = "owner console succession",
    ) -> UUID:
        """Register a new sealed break-glass credential.

        ``sealed_reference`` points at physically-secured material; it is never
        the credential itself.
        """
        owner = await repo.get_user(session, owner_user_id)
        if owner is None or not owner.is_owner:
            raise NotOwnerError("only the owner may seal a break-glass credential")

        credential = BreakGlassCredential(
            id=uuid4(),
            holder_user_id=holder_user_id,
            purpose=purpose,
            sealed_reference=sealed_reference,
            created_at=datetime.now(UTC),
            last_invoked_at=None,
            status=BreakGlassStatus.SEALED.value,
        )
        session.add(credential)
        await session.flush()

        await record_event(
            session,
            actor_user_id=owner_user_id,
            entity_schema="identity",
            entity_table="break_glass_credentials",
            entity_id=credential.id,
            action="seal",
            after_state={
                "holder_user_id": str(holder_user_id),
                "purpose": purpose,
                "status": BreakGlassStatus.SEALED.value,
            },
        )
        return credential.id

    async def invoke_break_glass(
        self,
        session: AsyncSession,
        *,
        credential_id: UUID,
        invoking_user_id: UUID,
        reason: str,
        now: datetime | None = None,
    ) -> BreakGlassGrant:
        """Invoke a sealed credential.

        Authorisation here is holder identity, deliberately **not** owner
        approval: the owner being unreachable is the condition that triggers
        this, so requiring their sign-off would make the mechanism useless
        exactly when it is needed.

        The caller must have completed step-up
        (``SensitiveAction.BREAK_GLASS_INVOKE``) before reaching here.
        """
        credential = await session.get(BreakGlassCredential, credential_id)
        if credential is None:
            raise IdentityError(f"break-glass credential {credential_id} does not exist")

        grant = invoke_break_glass(
            credential_id=credential.id,
            holder_user_id=credential.holder_user_id,
            invoking_user_id=invoking_user_id,
            current_status=BreakGlassStatus(credential.status),
            reason=reason,
            now=now,
        )

        credential.status = BreakGlassStatus.INVOKED.value
        credential.last_invoked_at = grant.granted_at
        await session.flush()

        await record_event(
            session,
            actor_user_id=invoking_user_id,
            entity_schema="identity",
            entity_table="break_glass_credentials",
            entity_id=credential.id,
            action="break_glass_invoke",
            before_state={"status": BreakGlassStatus.SEALED.value},
            after_state={
                "status": BreakGlassStatus.INVOKED.value,
                "reason": grant.reason,
                "invoked_by": str(invoking_user_id),
                "granted_at": grant.granted_at,
                "expires_at": grant.expires_at,
            },
        )
        return grant

    async def revoke_break_glass(
        self, session: AsyncSession, *, actor_user_id: UUID, credential_id: UUID
    ) -> None:
        """Revoke a credential and terminate any session derived from it.

        Containment has to be at least as fast as invocation, so the holder's
        sessions are killed in the same transaction rather than left to expire.
        """
        credential = await session.get(BreakGlassCredential, credential_id)
        if credential is None:
            raise IdentityError(f"break-glass credential {credential_id} does not exist")

        before = credential.status
        credential.status = revoke_break_glass(BreakGlassStatus(before)).value
        await session.flush()

        from sqlalchemy import text

        await session.execute(
            text(
                "UPDATE identity.sessions SET revoked_at = now() "
                "WHERE user_id = :uid AND revoked_at IS NULL"
            ),
            {"uid": credential.holder_user_id},
        )

        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="identity",
            entity_table="break_glass_credentials",
            entity_id=credential.id,
            action="break_glass_revoke",
            before_state={"status": before},
            after_state={
                "status": credential.status,
                "holder_sessions_revoked": True,
            },
        )


async def enroll_device(
    session: AsyncSession,
    *,
    user_id: UUID,
    device_name: str | None,
    passkey_credential_id: str,
    public_key: str,
) -> UUID:
    """Register a device, pending owner approval.

    New devices always start in ``pending_approval`` and cannot authenticate
    until the owner approves them — Blueprint §15.
    """
    now = datetime.now(UTC)
    device = Device(
        id=uuid4(),
        user_id=user_id,
        device_name=device_name,
        passkey_credential_id=passkey_credential_id,
        public_key=public_key,
        sign_counter=0,
        trust_level=DeviceTrust.STANDARD.value,
        status="pending_approval",
        enrolled_at=now,
        enrolled_by=None,
        last_used_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(device)
    await session.flush()

    await record_event(
        session,
        actor_user_id=user_id,
        entity_schema="identity",
        entity_table="devices",
        entity_id=device.id,
        action="enroll",
        after_state={"status": "pending_approval", "device_name": device_name},
    )
    return device.id
