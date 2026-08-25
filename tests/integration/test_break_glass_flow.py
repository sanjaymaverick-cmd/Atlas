"""Break-glass, end to end.

Kickoff item 6: "a sealed credential a second trusted party can invoke if the
primary owner is unreachable, with the invocation itself logged as an audit
event."

The tests below check both halves of that: the mechanism works for the holder
without owner involvement, and every step lands in the audit chain.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.identity.break_glass import (
    DEFAULT_GRANT_TTL,
    InvalidTransitionError,
    NotTheHolderError,
)
from atlas.modules.identity.service import IdentityService, NotOwnerError
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def async_session(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _user(session: AsyncSession, *, owner: bool, name: str) -> UUID:
    user_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, :name, :email, :owner, 'active', 1)"
        ),
        {"id": user_id, "name": name, "email": f"{user_id}@example.com", "owner": owner},
    )
    await session.commit()
    return user_id


async def _chain(session: AsyncSession) -> list[AuditRecord]:
    rows = (
        await session.execute(
            text(
                "SELECT seq, entity_schema, entity_table, entity_id, action, "
                "after_state::text, occurred_at, prev_hash, record_hash "
                "FROM audit.audit_events ORDER BY seq"
            )
        )
    ).all()
    return [AuditRecord(*row) for row in rows]


class TestSealAndInvoke:
    async def test_holder_invokes_without_the_owner(self, async_session: AsyncSession) -> None:
        """The owner being unreachable is the triggering condition.

        Requiring their approval would make the mechanism useless exactly when
        it is needed, so invocation authorises on holder identity alone.
        """
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Company Secretary")

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="sealed envelope, safe deposit box 41",
        )
        await async_session.commit()

        grant = await service.invoke_break_glass(
            async_session,
            credential_id=credential_id,
            invoking_user_id=holder,
            reason="owner unreachable; RERA filing deadline today",
        )
        await async_session.commit()

        assert grant.holder_user_id == holder
        assert grant.expires_at - grant.granted_at == DEFAULT_GRANT_TTL

    async def test_only_the_owner_may_seal(self, async_session: AsyncSession) -> None:
        service = IdentityService()
        not_owner = await _user(async_session, owner=False, name="Someone")

        with pytest.raises(NotOwnerError):
            await service.seal_break_glass(
                async_session,
                owner_user_id=not_owner,
                holder_user_id=not_owner,
                sealed_reference="envelope",
            )
        await async_session.rollback()

    async def test_a_non_holder_cannot_invoke(self, async_session: AsyncSession) -> None:
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Holder")
        outsider = await _user(async_session, owner=False, name="Outsider")

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="envelope",
        )
        await async_session.commit()

        with pytest.raises(NotTheHolderError):
            await service.invoke_break_glass(
                async_session,
                credential_id=credential_id,
                invoking_user_id=outsider,
                reason="attempting escalation",
            )
        await async_session.rollback()

    async def test_a_used_credential_cannot_be_reused(self, async_session: AsyncSession) -> None:
        """One shot. Re-arming means issuing a new sealed credential."""
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Holder")

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="envelope",
        )
        await async_session.commit()
        await service.invoke_break_glass(
            async_session,
            credential_id=credential_id,
            invoking_user_id=holder,
            reason="first use",
        )
        await async_session.commit()

        with pytest.raises(InvalidTransitionError):
            await service.invoke_break_glass(
                async_session,
                credential_id=credential_id,
                invoking_user_id=holder,
                reason="second use",
            )


class TestInvocationIsAudited:
    async def test_every_step_lands_in_the_chain(self, async_session: AsyncSession) -> None:
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Holder")

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="envelope",
        )
        await async_session.commit()
        await service.invoke_break_glass(
            async_session,
            credential_id=credential_id,
            invoking_user_id=holder,
            reason="owner unreachable; bank mandate expiring",
        )
        await async_session.commit()
        await service.revoke_break_glass(
            async_session, actor_user_id=owner, credential_id=credential_id
        )
        await async_session.commit()

        chain = await _chain(async_session)
        assert [r.action for r in chain] == [
            "seal",
            "break_glass_invoke",
            "break_glass_revoke",
        ]
        assert verify_chain(chain) == 3

    async def test_the_stated_reason_is_recorded(self, async_session: AsyncSession) -> None:
        """An emergency escalation with no recorded cause is not auditable."""
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Holder")

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="envelope",
        )
        await async_session.commit()
        await service.invoke_break_glass(
            async_session,
            credential_id=credential_id,
            invoking_user_id=holder,
            reason="owner unreachable; RERA filing deadline today",
        )
        await async_session.commit()

        recorded = (
            await async_session.execute(
                text(
                    "SELECT after_state->>'reason', after_state->>'invoked_by' "
                    "FROM audit.audit_events WHERE action = 'break_glass_invoke'"
                )
            )
        ).one()
        assert recorded[0] == "owner unreachable; RERA filing deadline today"
        assert recorded[1] == str(holder)


class TestRevocationContains:
    async def test_revoking_kills_the_holders_sessions(self, async_session: AsyncSession) -> None:
        """Containment must be at least as fast as invocation."""
        service = IdentityService()
        owner = await _user(async_session, owner=True, name="Owner")
        holder = await _user(async_session, owner=False, name="Holder")

        # A device and a live session for the holder.
        device_id = uuid4()
        await async_session.execute(
            text(
                "INSERT INTO identity.devices "
                "(id, user_id, passkey_credential_id, public_key, sign_counter, "
                " trust_level, status) "
                "VALUES (:id, :uid, :cred, 'pk', 0, 'standard', 'active')"
            ),
            {"id": device_id, "uid": holder, "cred": f"cred-{device_id}"},
        )
        await async_session.execute(
            text(
                "INSERT INTO identity.sessions "
                "(id, user_id, device_id, session_token_hash, expires_at) "
                "VALUES (gen_random_uuid(), :uid, :did, 'hash', now() + interval '8 hours')"
            ),
            {"uid": holder, "did": device_id},
        )
        await async_session.commit()

        credential_id = await service.seal_break_glass(
            async_session,
            owner_user_id=owner,
            holder_user_id=holder,
            sealed_reference="envelope",
        )
        await async_session.commit()
        await service.invoke_break_glass(
            async_session,
            credential_id=credential_id,
            invoking_user_id=holder,
            reason="owner unreachable",
        )
        await async_session.commit()

        live = (
            await async_session.execute(
                text(
                    "SELECT count(*) FROM identity.sessions "
                    "WHERE user_id = :uid AND revoked_at IS NULL"
                ),
                {"uid": holder},
            )
        ).scalar_one()
        assert live == 1

        await service.revoke_break_glass(
            async_session, actor_user_id=owner, credential_id=credential_id
        )
        await async_session.commit()

        still_live = (
            await async_session.execute(
                text(
                    "SELECT count(*) FROM identity.sessions "
                    "WHERE user_id = :uid AND revoked_at IS NULL"
                ),
                {"uid": holder},
            )
        ).scalar_one()
        assert still_live == 0
