"""Phase 5 lifecycle transition serialization against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.service import ConstructionService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]

Lifecycle = Literal["activity", "template", "snag"]


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


class RowLockProbeIdentity(AllowAllIdentity):
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


async def _seed_lifecycles(
    session: AsyncSession,
) -> tuple[UUID, dict[Lifecycle, UUID]]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    activity_id, template_id, snag_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Lifecycle Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"lifecycle-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Lifecycle Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Lifecycle Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Lifecycle Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-LIFE-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(id, project_id, name, actual_start, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, 'Synthetic Lifecycle Activity', :actual_start, "
            "'in_progress', :actor_id, :actor_id, 1)"
        ),
        {
            "id": activity_id,
            "project_id": project_id,
            "actual_start": date(2026, 8, 23),
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspection_templates "
            "(id, project_id, work_package, template_name, checklist, status, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, 'synthetic', :name, '[]'::jsonb, 'draft', "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": template_id,
            "project_id": project_id,
            "name": f"Synthetic Lifecycle Template {template_id}",
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.snag_items "
            "(id, project_id, description, severity, assigned_to, status, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, 'SYNTHETIC PRIVATE SNAG', 'major', :actor_id, "
            "'assigned', :actor_id, :actor_id, 1)"
        ),
        {"id": snag_id, "project_id": project_id, "actor_id": actor_id},
    )
    await session.commit()
    return actor_id, {"activity": activity_id, "template": template_id, "snag": snag_id}


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


async def _transition(
    session: AsyncSession,
    identity: AllowAllIdentity,
    *,
    actor_id: UUID,
    lifecycle: Lifecycle,
    row_id: UUID,
    target_status: str,
) -> None:
    service = ConstructionService(identity)
    if lifecycle == "activity":
        await service.transition_activity(
            session,
            actor_user_id=actor_id,
            activity_id=row_id,
            target_status=target_status,
        )
    elif lifecycle == "template":
        await service.transition_template(
            session,
            actor_user_id=actor_id,
            template_id=row_id,
            target_status=target_status,
        )
    else:
        await service.transition_snag(
            session,
            actor_user_id=actor_id,
            snag_id=row_id,
            target_status=target_status,
        )


def _transition_cases() -> list[tuple[Lifecycle, str, str, str]]:
    return [
        ("activity", "completed", "delayed", "in_progress"),
        ("template", "retired", "active", "draft"),
        ("snag", "rectified", "rectified", "assigned"),
    ]


def _state_query(lifecycle: Lifecycle) -> str:
    if lifecycle == "activity":
        return "SELECT status, version FROM construction.schedule_activities WHERE id = :id"
    if lifecycle == "template":
        return "SELECT status, version FROM quality.inspection_templates WHERE id = :id"
    return "SELECT status, version FROM quality.snag_items WHERE id = :id"


@pytest.mark.parametrize(
    ("lifecycle", "first_target", "second_target", "initial_status"), _transition_cases()
)
async def test_lifecycle_transition_rollback_restores_state_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lifecycle: Lifecycle,
    first_target: str,
    second_target: str,
    initial_status: str,
) -> None:
    del second_target
    async with session_factory() as session:
        actor_id, ids = await _seed_lifecycles(session)
        await _transition(
            session,
            AllowAllIdentity(),
            actor_id=actor_id,
            lifecycle=lifecycle,
            row_id=ids[lifecycle],
            target_status=first_target,
        )
        await session.rollback()

        state = (await session.execute(text(_state_query(lifecycle)), {"id": ids[lifecycle]})).one()
        assert tuple(state) == (initial_status, 1)
        assert await _audit_chain(session) == []


@pytest.mark.parametrize(
    ("lifecycle", "first_target", "second_target", "initial_status"), _transition_cases()
)
async def test_concurrent_lifecycle_transitions_serialize_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lifecycle: Lifecycle,
    first_target: str,
    second_target: str,
    initial_status: str,
) -> None:
    del initial_status
    async with session_factory() as seed:
        actor_id, ids = await _seed_lifecycles(seed)
    identity = RowLockProbeIdentity()

    async def run(target_status: str) -> str:
        async with session_factory() as session:
            try:
                await _transition(
                    session,
                    identity,
                    actor_id=actor_id,
                    lifecycle=lifecycle,
                    row_id=ids[lifecycle],
                    target_status=target_status,
                )
                await session.commit()
                return "transitioned"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(run(first_target))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(run(second_target))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["conflict", "transitioned"]

    async with session_factory() as session:
        state = (await session.execute(text(_state_query(lifecycle)), {"id": ids[lifecycle]})).one()
        assert tuple(state) == (first_target, 2)
        chain = await _audit_chain(session)
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state
