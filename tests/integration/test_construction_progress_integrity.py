"""Phase 5 schedule-progress integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.schemas import ProgressCreate
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


class ActivityLockProbeIdentity(AllowAllIdentity):
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


async def _seed_activity(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id, activity_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Progress Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"progress-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Progress Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Progress Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Progress Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-PRG-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(id, project_id, name, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, 'Synthetic Progress Activity', 'in_progress', "
            ":actor_id, :actor_id, 1)"
        ),
        {"id": activity_id, "project_id": project_id, "actor_id": actor_id},
    )
    await session.commit()
    return actor_id, activity_id


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


async def _add_progress(
    session: AsyncSession,
    identity: AllowAllIdentity,
    *,
    actor_id: UUID,
    activity_id: UUID,
    progress_date: date,
    percent: Decimal,
    notes: str = "SYNTHETIC PRIVATE PROGRESS NOTES",
) -> None:
    await ConstructionService(identity).add_progress(
        session,
        actor_user_id=actor_id,
        activity_id=activity_id,
        data=ProgressCreate(progress_date=progress_date, percent_complete=percent, notes=notes),
    )


async def test_progress_is_chronological_monotonic_and_audited_minimally(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, activity_id = await _seed_activity(session)
        await _add_progress(
            session,
            AllowAllIdentity(),
            actor_id=actor_id,
            activity_id=activity_id,
            progress_date=date(2026, 8, 23),
            percent=Decimal("60"),
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state
        assert json.loads(chain[0].after_state)["percent_complete"] == "60"

        with pytest.raises(ConstructionConflictError, match="date must follow"):
            await _add_progress(
                session,
                AllowAllIdentity(),
                actor_id=actor_id,
                activity_id=activity_id,
                progress_date=date(2026, 8, 22),
                percent=Decimal("70"),
            )
        await session.rollback()

        with pytest.raises(ConstructionConflictError, match="may not decrease"):
            await _add_progress(
                session,
                AllowAllIdentity(),
                actor_id=actor_id,
                activity_id=activity_id,
                progress_date=date(2026, 8, 24),
                percent=Decimal("50"),
            )
        await session.rollback()
        assert len(await _audit_chain(session)) == 1


async def test_progress_rollback_removes_update_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, activity_id = await _seed_activity(session)
        await _add_progress(
            session,
            AllowAllIdentity(),
            actor_id=actor_id,
            activity_id=activity_id,
            progress_date=date(2026, 8, 23),
            percent=Decimal("40"),
        )
        await session.rollback()
        count = await session.scalar(
            text(
                "SELECT count(*) FROM construction.progress_updates "
                "WHERE schedule_activity_id = :activity_id"
            ),
            {"activity_id": activity_id},
        )
        assert count == 0
        assert await _audit_chain(session) == []


async def test_concurrent_progress_writers_serialize_on_activity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, activity_id = await _seed_activity(seed)
    identity = ActivityLockProbeIdentity()

    async def write(progress_date: date, percent: Decimal) -> str:
        async with session_factory() as session:
            try:
                await _add_progress(
                    session,
                    identity,
                    actor_id=actor_id,
                    activity_id=activity_id,
                    progress_date=progress_date,
                    percent=percent,
                )
                await session.commit()
                return "created"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(write(date(2026, 8, 23), Decimal("80")))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(write(date(2026, 8, 24), Decimal("50")))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["conflict", "created"]

    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT progress_date, percent_complete "
                    "FROM construction.progress_updates "
                    "WHERE schedule_activity_id = :activity_id"
                ),
                {"activity_id": activity_id},
            )
        ).all()
        assert rows == [(date(2026, 8, 23), Decimal("80.00"))]
        assert len(await _audit_chain(session)) == 1
