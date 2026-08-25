"""Identity service — the concrete ``IdentityContract``.

Owns authentication, devices, sessions, scoped roles and the break-glass
credential. Everything other modules are allowed to ask is here; everything
they are not allowed to ask is in ``repository.py`` and ``models.py``, which
they cannot import.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

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
from atlas.modules.identity.contracts import InvalidCeremonyError, WebAuthnError
from atlas.modules.identity.models import BreakGlassCredential, Device, Session, WebAuthnChallenge
from atlas.modules.identity.schemas import (
    AuthenticationOutcome,
    CeremonyOptions,
    DeviceSummary,
    RelyingParty,
    SessionContext,
    UserSummary,
)
from atlas.modules.identity.scoping import any_grant_covers
from atlas.modules.identity.sessions import expiry_from, hash_token, is_expired, issue_token
from atlas.modules.identity.webauthn_adapter import (
    ClonedAuthenticatorError,
    authentication_options,
    credential_id_from_authentication,
    is_enrollment_usable,
    registration_options,
    verify_authentication,
    verify_registration,
    verify_sign_counter,
)
from atlas.platform.access_control import DeviceTrust
from atlas.platform.audit.writer import record_event


class IdentityError(Exception):
    """Base class for Identity refusals."""


class UnknownDeviceError(IdentityError):
    pass


class NotOwnerError(IdentityError):
    """Raised when a non-owner attempts an owner-only action."""


CHALLENGE_TTL = timedelta(minutes=5)


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

    async def authenticate_session_token(
        self, session: AsyncSession, token: str
    ) -> SessionContext | None:
        """Authenticate an opaque session token without exposing its hash."""
        if not token:
            return None
        stored = await repo.get_session_by_token_hash(session, hash_token(token))
        if stored is None:
            return None
        context = await self.get_session(session, stored.id)
        if context is None:
            return None
        if (
            context.revoked_at is not None
            or is_expired(context.expires_at)
            or context.user_status != "active"
            or context.device_status != "active"
        ):
            return None
        return context

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

    async def begin_registration(
        self, session: AsyncSession, *, user_id: UUID, rp: RelyingParty
    ) -> CeremonyOptions:
        user = await repo.get_user(session, user_id)
        if user is None or user.status != "active":
            raise InvalidCeremonyError("registration user is unavailable")
        challenge, options = registration_options(
            rp=rp,
            user_id=user.id.bytes,
            user_name=user.email,
            user_display_name=user.full_name,
        )
        row = self._new_challenge(user_id=user.id, kind="registration", challenge=challenge)
        session.add(row)
        await session.flush()
        await record_event(
            session,
            actor_user_id=user.id,
            entity_schema="identity",
            entity_table="webauthn_challenges",
            entity_id=row.id,
            action="issue_registration_challenge",
            after_state={"ceremony_type": row.ceremony_type, "expires_at": row.expires_at},
        )
        return CeremonyOptions(ceremony_id=row.id, public_key=options)

    async def complete_registration(
        self,
        session: AsyncSession,
        *,
        ceremony_id: UUID,
        credential: dict[str, Any],
        device_name: str | None,
        rp: RelyingParty,
    ) -> UUID:
        row = await self._consume_challenge(session, ceremony_id, "registration")
        if row.user_id is None:
            raise InvalidCeremonyError("registration challenge has no user")
        verified = verify_registration(
            rp=rp,
            expected_challenge=base64url_to_bytes(row.challenge),
            credential=credential,
        )
        return await enroll_device(
            session,
            user_id=row.user_id,
            device_name=device_name,
            passkey_credential_id=verified.credential_id,
            public_key=verified.public_key,
            sign_counter=verified.sign_count,
        )

    async def begin_authentication(
        self, session: AsyncSession, *, rp: RelyingParty
    ) -> CeremonyOptions:
        challenge, options = authentication_options(rp=rp)
        row = self._new_challenge(user_id=None, kind="authentication", challenge=challenge)
        session.add(row)
        await session.flush()
        await record_event(
            session,
            actor_user_id=None,
            entity_schema="identity",
            entity_table="webauthn_challenges",
            entity_id=row.id,
            action="issue_authentication_challenge",
            after_state={"ceremony_type": row.ceremony_type, "expires_at": row.expires_at},
        )
        return CeremonyOptions(ceremony_id=row.id, public_key=options)

    async def complete_authentication(
        self,
        session: AsyncSession,
        *,
        ceremony_id: UUID,
        credential: dict[str, Any],
        rp: RelyingParty,
    ) -> AuthenticationOutcome:
        row = await self._consume_challenge(session, ceremony_id, "authentication")
        credential_id = credential_id_from_authentication(credential)
        device = await repo.get_device_by_credential_id(session, credential_id)
        if device is None or not is_enrollment_usable(device.status):
            raise WebAuthnError("credential is not available for authentication")
        verified = verify_authentication(
            rp=rp,
            expected_challenge=base64url_to_bytes(row.challenge),
            credential=credential,
            credential_public_key=device.public_key,
            current_sign_count=0,
        )
        try:
            new_counter = verify_sign_counter(
                stored=device.sign_counter, presented=verified.sign_count
            )
        except ClonedAuthenticatorError:
            await self.flag_cloned_device(
                session,
                device_id=device.id,
                stored=device.sign_counter,
                presented=verified.sign_count,
            )
            return AuthenticationOutcome(session_token=None, expires_at=None, clone_detected=True)

        now = datetime.now(UTC)
        previous_counter = device.sign_counter
        previous_last_used = device.last_used_at
        device.sign_counter = new_counter
        device.last_used_at = now
        await session.flush()
        await record_event(
            session,
            actor_user_id=device.user_id,
            entity_schema="identity",
            entity_table="devices",
            entity_id=device.id,
            action="authenticate",
            before_state={
                "sign_counter": previous_counter,
                "last_used_at": previous_last_used,
            },
            after_state={"sign_counter": new_counter, "last_used_at": now},
        )
        token, token_hash = issue_token()
        expires_at = expiry_from(now)
        login_session = Session(
            id=uuid4(),
            user_id=device.user_id,
            device_id=device.id,
            session_token_hash=token_hash,
            risk_score=0,
            step_up_verified=False,
            step_up_verified_at=None,
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
        session.add(login_session)
        await session.flush()
        await record_event(
            session,
            actor_user_id=device.user_id,
            entity_schema="identity",
            entity_table="sessions",
            entity_id=login_session.id,
            action="authenticate",
            after_state={"device_id": str(device.id), "expires_at": expires_at},
        )
        return AuthenticationOutcome(session_token=token, expires_at=expires_at)

    @staticmethod
    def _new_challenge(*, user_id: UUID | None, kind: str, challenge: bytes) -> WebAuthnChallenge:
        now = datetime.now(UTC)
        return WebAuthnChallenge(
            id=uuid4(),
            user_id=user_id,
            ceremony_type=kind,
            challenge=bytes_to_base64url(challenge),
            expires_at=now + CHALLENGE_TTL,
            used_at=None,
            created_at=now,
        )

    @staticmethod
    async def _consume_challenge(
        session: AsyncSession, challenge_id: UUID, expected_kind: str
    ) -> WebAuthnChallenge:
        row = await repo.get_challenge_for_update(session, challenge_id)
        now = datetime.now(UTC)
        if (
            row is None
            or row.ceremony_type != expected_kind
            or row.used_at is not None
            or row.expires_at <= now
        ):
            raise InvalidCeremonyError("ceremony is unknown, expired, or already used")
        row.used_at = now
        await session.flush()
        await record_event(
            session,
            actor_user_id=row.user_id,
            entity_schema="identity",
            entity_table="webauthn_challenges",
            entity_id=row.id,
            action="consume_challenge",
            before_state={"used_at": None},
            after_state={"used_at": now, "ceremony_type": row.ceremony_type},
        )
        return row

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

        before = {"status": device.status, "sign_counter": device.sign_counter}
        device.status = "revoked"
        await session.flush()
        await record_event(
            session,
            actor_user_id=None,  # detected by the system, not performed by a user
            entity_schema="identity",
            entity_table="devices",
            entity_id=device.id,
            action="revoke_suspected_clone",
            before_state=before,
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
    sign_counter: int = 0,
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
        sign_counter=sign_counter,
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
