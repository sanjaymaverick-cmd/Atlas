"""Phase 5 meeting workflow integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.schemas import MeetingActionCreate, MeetingCreate
from atlas.modules.construction.service import ConstructionService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]


class AllowAllIdentity:
    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return True


class MeetingLockProbeIdentity(AllowAllIdentity):
    def __init__(self) -> None:
        self.calls = 0
        self.first_has_lock = asyncio.Event()
        self.release_first = asyncio.Event()

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.calls += 1
        if self.calls == 1:
            self.first_has_lock.set()
            await self.release_first.wait()
        return True


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_scope(session: AsyncSession) -> tuple[UUID, UUID, UUID]:
    actor_id, group_id, entity_id, project_id, other_project_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Meeting Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"meeting-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Meeting Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Meeting Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project, :entity, 'Synthetic Meeting Project', :code, 'active', 1), "
            "(:other, :entity, 'Synthetic Other Meeting Project', :other_code, 'active', 1)"
        ),
        {
            "project": project_id,
            "other": other_project_id,
            "entity": entity_id,
            "code": f"SYN-MEET-{project_id}",
            "other_code": f"SYN-MEET-{other_project_id}",
        },
    )
    await session.commit()
    return actor_id, project_id, other_project_id


async def _create_meeting(
    session: AsyncSession,
    *,
    actor_id: UUID,
    project_id: UUID,
    identity: AllowAllIdentity | None = None,
) -> UUID:
    result = await ConstructionService(identity or AllowAllIdentity()).create_meeting(
        session,
        actor_user_id=actor_id,
        data=MeetingCreate(
            project_id=project_id,
            meeting_date=date(2026, 8, 24),
            participant_user_ids=(actor_id, actor_id),
            decisions=("SYNTHETIC PRIVATE MEETING DECISION",),
        ),
    )
    return result.id


async def _audit_chain(session: AsyncSession) -> list[AuditRecord]:
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


async def test_meeting_workflow_commits_versioned_minimized_audit_and_archives_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _ = await _seed_scope(session)
        service = ConstructionService(AllowAllIdentity())
        meeting_id = await _create_meeting(session, actor_id=actor_id, project_id=project_id)
        action = await service.create_meeting_action(
            session,
            actor_user_id=actor_id,
            meeting_id=meeting_id,
            data=MeetingActionCreate(
                description="SYNTHETIC PRIVATE ACTION DESCRIPTION",
                responsible_user_id=actor_id,
                due_date=date(2026, 8, 25),
            ),
        )
        await service.transition_meeting_action(
            session,
            actor_user_id=actor_id,
            action_id=action.id,
            target_status="done",
        )
        await service.close_meeting(session, actor_user_id=actor_id, meeting_id=meeting_id)
        await service.archive_meeting_action(session, actor_user_id=actor_id, action_id=action.id)
        await service.archive_meeting(session, actor_user_id=actor_id, meeting_id=meeting_id)
        await session.commit()

        retried_action = await service.archive_meeting_action(
            session, actor_user_id=actor_id, action_id=action.id
        )
        retried_meeting = await service.archive_meeting(
            session, actor_user_id=actor_id, meeting_id=meeting_id
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert retried_action.version == 3 and retried_action.archived_at is not None
        assert retried_meeting.version == 3 and retried_meeting.archived_at is not None
        assert [event.action for event in chain] == [
            "create",
            "create",
            "transition",
            "close",
            "archive",
            "archive",
        ]
        assert verify_chain(chain) == len(chain)
        assert "SYNTHETIC PRIVATE" not in "".join(event.after_state or "" for event in chain)


async def test_meeting_refuses_close_with_unfinished_action(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _ = await _seed_scope(session)
        service = ConstructionService(AllowAllIdentity())
        meeting_id = await _create_meeting(session, actor_id=actor_id, project_id=project_id)
        action = await service.create_meeting_action(
            session,
            actor_user_id=actor_id,
            meeting_id=meeting_id,
            data=MeetingActionCreate("SYNTHETIC PRIVATE OPEN ACTION"),
        )
        await session.commit()

        with pytest.raises(ConstructionConflictError, match="closed meeting"):
            await service.archive_meeting(session, actor_user_id=actor_id, meeting_id=meeting_id)
        with pytest.raises(ConstructionConflictError, match="done meeting action"):
            await service.archive_meeting_action(
                session, actor_user_id=actor_id, action_id=action.id
            )
        with pytest.raises(ConstructionConflictError, match="unfinished"):
            await service.close_meeting(session, actor_user_id=actor_id, meeting_id=meeting_id)
        await session.rollback()
        state = await session.scalar(
            text("SELECT status FROM construction.meeting_registers WHERE id = :id"),
            {"id": meeting_id},
        )
        assert state == "recorded"
        assert len(await _audit_chain(session)) == 2


async def test_meeting_create_and_action_rollback_together_with_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _ = await _seed_scope(session)
        service = ConstructionService(AllowAllIdentity())
        meeting_id = await _create_meeting(session, actor_id=actor_id, project_id=project_id)
        action = await service.create_meeting_action(
            session,
            actor_user_id=actor_id,
            meeting_id=meeting_id,
            data=MeetingActionCreate("SYNTHETIC PRIVATE ROLLBACK ACTION"),
        )
        await session.rollback()

        meeting_count = await session.scalar(
            text("SELECT count(*) FROM construction.meeting_registers WHERE id = :id"),
            {"id": meeting_id},
        )
        action_count = await session.scalar(
            text("SELECT count(*) FROM construction.meeting_action_items WHERE id = :id"),
            {"id": action.id},
        )
        assert (meeting_count, action_count) == (0, 0)
        assert await _audit_chain(session) == []


async def test_create_action_serializes_with_meeting_close(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, project_id, _ = await _seed_scope(seed)
        meeting_id = await _create_meeting(seed, actor_id=actor_id, project_id=project_id)
        await seed.commit()
    identity = MeetingLockProbeIdentity()

    async def create_action() -> str:
        async with session_factory() as session:
            await ConstructionService(identity).create_meeting_action(
                session,
                actor_user_id=actor_id,
                meeting_id=meeting_id,
                data=MeetingActionCreate("SYNTHETIC PRIVATE CONCURRENT ACTION"),
            )
            await session.commit()
            return "created"

    async def close() -> str:
        async with session_factory() as session:
            try:
                await ConstructionService(identity).close_meeting(
                    session, actor_user_id=actor_id, meeting_id=meeting_id
                )
                await session.commit()
                return "closed"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    creator = asyncio.create_task(create_action())
    await identity.first_has_lock.wait()
    closer = asyncio.create_task(close())
    await asyncio.sleep(0.1)
    assert not closer.done()
    identity.release_first.set()
    assert await creator == "created"
    assert await closer == "conflict"


def test_database_rejects_cross_project_meeting_action(db: Any) -> None:
    actor_id, project_id, other_project_id = uuid4(), uuid4(), uuid4()
    group_id, entity_id, meeting_id = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO identity.users (id, full_name, email, status, version) "
        "VALUES (%(id)s, 'Synthetic DB Meeting Actor', %(email)s, 'active', 1)",
        {"id": actor_id, "email": f"db-meeting-{actor_id}@example.invalid"},
    )
    db.execute(
        "INSERT INTO organization.business_groups (id, name, status, version) "
        "VALUES (%(id)s, 'Synthetic DB Meeting Group', 'active', 1)",
        {"id": group_id},
    )
    db.execute(
        "INSERT INTO organization.legal_entities "
        "(id, business_group_id, name, status, version) "
        "VALUES (%(id)s, %(group)s, 'Synthetic DB Meeting Entity', 'active', 1)",
        {"id": entity_id, "group": group_id},
    )
    db.execute(
        "INSERT INTO organization.projects "
        "(id, legal_entity_id, name, code, status, version) VALUES "
        "(%(project)s, %(entity)s, 'Synthetic DB Meeting Project', %(code)s, 'active', 1), "
        "(%(other)s, %(entity)s, 'Synthetic DB Other Project', %(other_code)s, 'active', 1)",
        {
            "project": project_id,
            "other": other_project_id,
            "entity": entity_id,
            "code": f"SYN-DB-MEET-{project_id}",
            "other_code": f"SYN-DB-MEET-{other_project_id}",
        },
    )
    db.execute(
        "INSERT INTO construction.meeting_registers "
        "(id, project_id, meeting_date, status, version) "
        "VALUES (%(id)s, %(project)s, %(date)s, 'recorded', 1)",
        {"id": meeting_id, "project": project_id, "date": date(2026, 8, 24)},
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute(
            "INSERT INTO construction.meeting_action_items "
            "(meeting_register_id, project_id, description, status, version) "
            "VALUES (%(meeting)s, %(project)s, 'Synthetic Invalid Action', 'open', 1)",
            {"meeting": meeting_id, "project": other_project_id},
        )
