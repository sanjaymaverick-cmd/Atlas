"""Project CRUD writes audit events, and the chain still verifies.

Kickoff item 5: "every mutating action writes an audit.audit_events row via
the hash-chain trigger". This exercises that through the real service against a
real database, rather than asserting it about the writer in isolation.

It also covers kickoff item 4 — CRUD scoped by ``identity.user_roles`` — by
driving the service with a stub Identity that answers the scoping question, and
checking the service refuses when the answer is no.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.identity.schemas import DeviceSummary, SessionContext, UserSummary
from atlas.modules.organization.schemas import ProjectCreate, ProjectUpdate
from atlas.modules.organization.service import (
    NotAuthorisedError,
    NotFoundError,
    OrganizationService,
)
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]


class StubIdentity:
    """Identity double that answers the scoping question from a fixed rule.

    Organization only ever asks ``check_scoped_role``, so a stub is enough to
    drive it — which is itself the point of the contract boundary: Organization
    can be tested without Identity's tables existing at all.
    """

    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[dict[str, Any]] = []

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.calls.append(
            {
                "user_id": user_id,
                "permission_code": permission_code,
                "legal_entity_id": legal_entity_id,
                "project_id": project_id,
            }
        )
        return self.allow

    async def get_user(
        self, session: AsyncSession, user_id: UUID
    ) -> UserSummary | None:  # pragma: no cover
        return None

    async def get_session(
        self, session: AsyncSession, session_id: UUID
    ) -> SessionContext | None:  # pragma: no cover
        return None

    async def list_pending_devices(
        self, session: AsyncSession
    ) -> list[DeviceSummary]:  # pragma: no cover
        return []

    async def authenticate_session_token(
        self, session: AsyncSession, token: str
    ) -> SessionContext | None:  # pragma: no cover
        return None


@pytest.fixture
async def async_session(database_url: str, db: Any) -> Any:
    """An async session over the same database the ``db`` fixture cleaned."""
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_user(session: AsyncSession) -> UUID:
    """Create a real user to act as the mutation's actor.

    organization.projects.created_by is a foreign key onto identity.users, so
    the actor has to exist. That constraint is doing real work: it means an
    audit trail can never attribute a change to a user who was never in the
    system.
    """
    from sqlalchemy import text

    user_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Test Actor', :email, false, 'active', 1)"
        ),
        {"id": user_id, "email": f"actor-{user_id}@example.com"},
    )
    await session.commit()
    return user_id


async def _seed_entity(session: AsyncSession) -> UUID:
    """Create a business group and legal entity to hang projects off."""
    from sqlalchemy import text

    group_id = uuid4()
    entity_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Test Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Entity A', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.commit()
    return entity_id


async def _chain(session: AsyncSession) -> list[AuditRecord]:
    from sqlalchemy import text

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


class TestMutationsAreAudited:
    async def test_create_update_archive_each_write_one_event(
        self, async_session: AsyncSession
    ) -> None:
        entity_id = await _seed_entity(async_session)
        service = OrganizationService(StubIdentity())
        actor = await _seed_user(async_session)

        created = await service.create_project(
            async_session,
            actor_user_id=actor,
            data=ProjectCreate(
                legal_entity_id=entity_id, name="Riverside", code="RVR-1", city="Pune"
            ),
        )
        await service.update_project(
            async_session,
            actor_user_id=actor,
            project_id=created.id,
            data=ProjectUpdate(city="Mumbai", status="active"),
        )
        await service.archive_project(async_session, actor_user_id=actor, project_id=created.id)
        await async_session.commit()

        chain = await _chain(async_session)
        assert [r.action for r in chain] == ["create", "update", "archive"]
        assert all(r.entity_id == created.id for r in chain)
        # The chain must still verify after real business writes.
        assert verify_chain(chain) == 3

    async def test_update_records_prior_values_and_bumps_version(
        self, async_session: AsyncSession
    ) -> None:
        """'No silent overwrites': the old value survives in before_state."""
        from sqlalchemy import text

        entity_id = await _seed_entity(async_session)
        service = OrganizationService(StubIdentity())
        actor = await _seed_user(async_session)

        created = await service.create_project(
            async_session,
            actor_user_id=actor,
            data=ProjectCreate(legal_entity_id=entity_id, name="Riverside", code="RVR-2"),
        )
        assert created.version == 1

        updated = await service.update_project(
            async_session,
            actor_user_id=actor,
            project_id=created.id,
            data=ProjectUpdate(name="Riverside Phase II"),
        )
        await async_session.commit()
        assert updated.version == 2

        before = (
            await async_session.execute(
                text("SELECT before_state->>'name' FROM audit.audit_events WHERE action = 'update'")
            )
        ).scalar_one()
        assert before == "Riverside"

    async def test_a_failed_mutation_writes_no_audit_event(
        self, async_session: AsyncSession
    ) -> None:
        """The event and the change share a transaction, so both or neither."""
        service = OrganizationService(StubIdentity())
        with pytest.raises(NotFoundError):
            await service.create_project(
                async_session,
                # Never reaches the insert: the legal entity check fails first.
                actor_user_id=uuid4(),
                data=ProjectCreate(legal_entity_id=uuid4(), name="Nowhere", code="NON-1"),
            )
        await async_session.rollback()
        assert await _chain(async_session) == []


class TestScoping:
    async def test_refused_when_identity_says_no(self, async_session: AsyncSession) -> None:
        entity_id = await _seed_entity(async_session)
        service = OrganizationService(StubIdentity(allow=False))

        with pytest.raises(NotAuthorisedError):
            await service.create_project(
                async_session,
                actor_user_id=uuid4(),
                data=ProjectCreate(legal_entity_id=entity_id, name="Riverside", code="RVR-3"),
            )
        await async_session.rollback()
        assert await _chain(async_session) == []

    async def test_the_scope_is_passed_to_identity(self, async_session: AsyncSession) -> None:
        """Organization asks; it does not decide.

        The entity and project reach Identity intact, which is what lets the
        scoping rule live in one place.
        """
        entity_id = await _seed_entity(async_session)
        identity = StubIdentity()
        service = OrganizationService(identity)
        actor = await _seed_user(async_session)

        created = await service.create_project(
            async_session,
            actor_user_id=actor,
            data=ProjectCreate(legal_entity_id=entity_id, name="Riverside", code="RVR-4"),
        )
        await service.update_project(
            async_session,
            actor_user_id=actor,
            project_id=created.id,
            data=ProjectUpdate(city="Nashik"),
        )
        await async_session.commit()

        create_call, update_call = identity.calls
        assert create_call["permission_code"] == "project.create"
        assert create_call["legal_entity_id"] == entity_id
        assert create_call["project_id"] is None

        assert update_call["permission_code"] == "project.update"
        assert update_call["legal_entity_id"] == entity_id
        assert update_call["project_id"] == created.id

    async def test_list_requires_entity_scoped_read_permission(
        self, async_session: AsyncSession
    ) -> None:
        entity_id = await _seed_entity(async_session)
        identity = StubIdentity(allow=False)
        service = OrganizationService(identity)

        with pytest.raises(NotAuthorisedError):
            await service.list_projects(
                async_session, actor_user_id=uuid4(), legal_entity_id=entity_id
            )
        assert identity.calls[0]["permission_code"] == "project.read"
        assert identity.calls[0]["legal_entity_id"] == entity_id

    async def test_list_rejects_an_unknown_legal_entity(self, async_session: AsyncSession) -> None:
        service = OrganizationService(StubIdentity())
        with pytest.raises(NotFoundError, match="legal entity"):
            await service.list_projects(
                async_session, actor_user_id=uuid4(), legal_entity_id=uuid4()
            )


class TestArchiveNotDelete:
    async def test_archived_project_still_exists(self, async_session: AsyncSession) -> None:
        entity_id = await _seed_entity(async_session)
        service = OrganizationService(StubIdentity())
        actor = await _seed_user(async_session)

        created = await service.create_project(
            async_session,
            actor_user_id=actor,
            data=ProjectCreate(legal_entity_id=entity_id, name="Riverside", code="RVR-5"),
        )
        archived = await service.archive_project(
            async_session, actor_user_id=actor, project_id=created.id
        )
        await async_session.commit()

        assert archived.is_archived
        # Still fetchable, still auditable — the row was not removed.
        assert (
            await service.get_project(async_session, actor_user_id=actor, project_id=created.id)
        ).id == created.id
        assert (
            await service.list_projects(
                async_session, actor_user_id=actor, legal_entity_id=entity_id
            )
            == []
        )

    async def test_archived_project_cannot_be_edited(self, async_session: AsyncSession) -> None:
        entity_id = await _seed_entity(async_session)
        service = OrganizationService(StubIdentity())
        actor = await _seed_user(async_session)

        created = await service.create_project(
            async_session,
            actor_user_id=actor,
            data=ProjectCreate(legal_entity_id=entity_id, name="Riverside", code="RVR-6"),
        )
        await service.archive_project(async_session, actor_user_id=actor, project_id=created.id)
        await async_session.commit()

        with pytest.raises(NotAuthorisedError, match="archived"):
            await service.update_project(
                async_session,
                actor_user_id=actor,
                project_id=created.id,
                data=ProjectUpdate(city="Pune"),
            )
