"""Phase 5 creation and audit atomicity against PostgreSQL."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.schemas import (
    ChecklistItem,
    EhsCreate,
    InspectionCreate,
    ScheduleCreate,
    SiteDiaryCreate,
    SnagCreate,
    TemplateCreate,
)
from atlas.modules.construction.service import ConstructionService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]

CreationKind = Literal["activity", "diary", "ehs", "template", "inspection", "snag"]
KINDS: tuple[CreationKind, ...] = (
    "activity",
    "diary",
    "ehs",
    "template",
    "inspection",
    "snag",
)


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


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_scope(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Creation Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"creation-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Creation Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Creation Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Creation Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-CREATE-{project_id}"},
    )
    await session.commit()
    return actor_id, project_id


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


def _count_query(kind: CreationKind) -> str:
    return {
        "activity": "SELECT count(*) FROM construction.schedule_activities WHERE id = :id",
        "diary": "SELECT count(*) FROM construction.site_diary_entries WHERE id = :id",
        "ehs": "SELECT count(*) FROM construction.ehs_incidents WHERE id = :id",
        "template": "SELECT count(*) FROM quality.inspection_templates WHERE id = :id",
        "inspection": "SELECT count(*) FROM quality.inspections WHERE id = :id",
        "snag": "SELECT count(*) FROM quality.snag_items WHERE id = :id",
    }[kind]


async def _create(
    session: AsyncSession,
    *,
    actor_id: UUID,
    project_id: UUID,
    kind: CreationKind,
) -> UUID:
    service = ConstructionService(AllowAllIdentity())
    if kind == "activity":
        result = await service.create_activity(
            session,
            actor_user_id=actor_id,
            data=ScheduleCreate(
                project_id=project_id,
                name="Synthetic Creation Activity",
                planned_start=date(2026, 8, 23),
                planned_end=date(2026, 8, 24),
            ),
        )
    elif kind == "diary":
        result = await service.submit_site_diary(
            session,
            actor_user_id=actor_id,
            data=SiteDiaryCreate(
                project_id=project_id,
                entry_date=date(2026, 8, 23),
                client_record_id=uuid4(),
                device_recorded_at=datetime(2026, 8, 23, 10, tzinfo=UTC),
                weather="SYNTHETIC PRIVATE WEATHER NOTE",
                labour_strength={"synthetic_trade": 4},
                materials_received=(),
                materials_consumed=(),
                equipment_breakdowns="SYNTHETIC PRIVATE BREAKDOWN NOTE",
                visitor_count=2,
                site_instructions="SYNTHETIC PRIVATE SITE INSTRUCTION",
                delays_and_reasons="SYNTHETIC PRIVATE DELAY NOTE",
            ),
        )
    elif kind == "ehs":
        result = await service.create_ehs_incident(
            session,
            actor_user_id=actor_id,
            data=EhsCreate(
                project_id=project_id,
                incident_date=date(2026, 8, 23),
                severity="minor",
                description="SYNTHETIC PRIVATE INCIDENT NARRATIVE",
            ),
        )
    elif kind == "template":
        result = await service.create_template(
            session,
            actor_user_id=actor_id,
            data=TemplateCreate(
                project_id=project_id,
                work_package="synthetic",
                template_name=f"Synthetic Creation Template {uuid4()}",
                checklist=(ChecklistItem("SYNTHETIC PRIVATE CHECKLIST ITEM"),),
            ),
        )
    elif kind == "inspection":
        result = await service.schedule_inspection(
            session,
            actor_user_id=actor_id,
            data=InspectionCreate(
                project_id=project_id,
                template_id=None,
                inspector_id=actor_id,
            ),
        )
    else:
        result = await service.create_snag(
            session,
            actor_user_id=actor_id,
            data=SnagCreate(
                project_id=project_id,
                description="SYNTHETIC PRIVATE SNAG DESCRIPTION",
                severity="minor",
            ),
        )
    return result.id


@pytest.mark.parametrize("kind", KINDS)
async def test_creation_commits_one_row_and_one_valid_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession], *, kind: CreationKind
) -> None:
    async with session_factory() as session:
        actor_id, project_id = await _seed_scope(session)
        row_id = await _create(
            session,
            actor_id=actor_id,
            project_id=project_id,
            kind=kind,
        )
        await session.commit()

        count = await session.scalar(text(_count_query(kind)), {"id": row_id})
        chain = await _audit_chain(session)
        assert count == 1
        expected_action = "submit" if kind == "diary" else "create"
        assert len(chain) == 1 and chain[0].action == expected_action
        assert chain[0].entity_id == row_id and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state


@pytest.mark.parametrize("kind", KINDS)
async def test_creation_rollback_removes_row_and_audit(
    session_factory: async_sessionmaker[AsyncSession], *, kind: CreationKind
) -> None:
    async with session_factory() as session:
        actor_id, project_id = await _seed_scope(session)
        row_id = await _create(
            session,
            actor_id=actor_id,
            project_id=project_id,
            kind=kind,
        )
        await session.rollback()

        count = await session.scalar(text(_count_query(kind)), {"id": row_id})
        assert count == 0
        assert await _audit_chain(session) == []
