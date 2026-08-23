"""Phase 5 archival, versioning, and audit atomicity against PostgreSQL."""

from __future__ import annotations

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

RecordKind = Literal["activity", "progress", "diary", "ehs", "template", "inspection", "snag"]


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


async def _seed_records(session: AsyncSession) -> dict[RecordKind, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    ids: dict[RecordKind, UUID] = {
        "activity": uuid4(),
        "progress": uuid4(),
        "diary": uuid4(),
        "ehs": uuid4(),
        "template": uuid4(),
        "inspection": uuid4(),
        "snag": uuid4(),
    }
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Archive Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"archive-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Archive Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Archive Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Archive Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-ARC-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(id, project_id, name, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, 'Synthetic Completed Activity', 'completed', "
            ":actor_id, :actor_id, 1)"
        ),
        {"id": ids["activity"], "project_id": project_id, "actor_id": actor_id},
    )
    await session.execute(
        text(
            "INSERT INTO construction.progress_updates "
            "(id, project_id, schedule_activity_id, progress_date, percent_complete, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, :activity_id, DATE '2026-08-23', 80, :actor_id, :actor_id, 1)"
        ),
        {
            "id": ids["progress"],
            "project_id": project_id,
            "activity_id": ids["activity"],
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO construction.site_diary_entries "
            "(id, project_id, entry_date, client_record_id, status, created_by, updated_by, "
            "version) VALUES "
            "(:id, :project_id, DATE '2026-08-23', :client_id, 'submitted', "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": ids["diary"],
            "project_id": project_id,
            "client_id": uuid4(),
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO construction.ehs_incidents "
            "(id, project_id, site_diary_entry_id, incident_date, severity, corrective_action, "
            "status, created_by, updated_by, version) VALUES "
            "(:id, :project_id, :diary_id, DATE '2026-08-23', 'minor', "
            "'SYNTHETIC PRIVATE CORRECTIVE ACTION', 'closed', :actor_id, :actor_id, 1)"
        ),
        {
            "id": ids["ehs"],
            "project_id": project_id,
            "diary_id": ids["diary"],
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspection_templates "
            "(id, project_id, work_package, template_name, checklist, status, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, 'synthetic', :name, '[]'::jsonb, 'retired', "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": ids["template"],
            "project_id": project_id,
            "name": f"Synthetic Retired Template {ids['template']}",
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspections "
            "(id, project_id, result, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, 'pass', 'completed', :actor_id, :actor_id, 1)"
        ),
        {"id": ids["inspection"], "project_id": project_id, "actor_id": actor_id},
    )
    await session.execute(
        text(
            "INSERT INTO quality.snag_items "
            "(id, project_id, inspection_id, description, severity, status, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, :inspection_id, 'SYNTHETIC PRIVATE CLOSED SNAG', "
            "'minor', 'closed', :actor_id, :actor_id, 1)"
        ),
        {
            "id": ids["snag"],
            "project_id": project_id,
            "inspection_id": ids["inspection"],
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return ids


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


def _state_query(kind: RecordKind) -> str:
    return {
        "activity": (
            "SELECT version, archived_at FROM construction.schedule_activities WHERE id = :id"
        ),
        "progress": "SELECT version, archived_at FROM construction.progress_updates WHERE id = :id",
        "diary": "SELECT version, archived_at FROM construction.site_diary_entries WHERE id = :id",
        "ehs": "SELECT version, archived_at FROM construction.ehs_incidents WHERE id = :id",
        "template": "SELECT version, archived_at FROM quality.inspection_templates WHERE id = :id",
        "inspection": "SELECT version, archived_at FROM quality.inspections WHERE id = :id",
        "snag": "SELECT version, archived_at FROM quality.snag_items WHERE id = :id",
    }[kind]


def _status_update(kind: RecordKind) -> str:
    return {
        "activity": "UPDATE construction.schedule_activities SET status = :status WHERE id = :id",
        "progress": "UPDATE construction.progress_updates SET version = version WHERE id = :id",
        "diary": "UPDATE construction.site_diary_entries SET status = :status WHERE id = :id",
        "ehs": "UPDATE construction.ehs_incidents SET status = :status WHERE id = :id",
        "template": "UPDATE quality.inspection_templates SET status = :status WHERE id = :id",
        "inspection": "UPDATE quality.inspections SET status = :status WHERE id = :id",
        "snag": "UPDATE quality.snag_items SET status = :status WHERE id = :id",
    }[kind]


async def _archive(
    session: AsyncSession, *, actor_id: UUID, kind: RecordKind, row_id: UUID
) -> tuple[int, object | None]:
    service = ConstructionService(AllowAllIdentity())
    if kind == "activity":
        result = await service.archive_activity(session, actor_user_id=actor_id, activity_id=row_id)
    elif kind == "progress":
        result = await service.archive_progress(session, actor_user_id=actor_id, progress_id=row_id)
    elif kind == "diary":
        result = await service.archive_site_diary(session, actor_user_id=actor_id, diary_id=row_id)
    elif kind == "ehs":
        result = await service.archive_ehs_incident(
            session, actor_user_id=actor_id, incident_id=row_id
        )
    elif kind == "template":
        result = await service.archive_template(session, actor_user_id=actor_id, template_id=row_id)
    elif kind == "inspection":
        result = await service.archive_inspection(
            session, actor_user_id=actor_id, inspection_id=row_id
        )
    else:
        result = await service.archive_snag(session, actor_user_id=actor_id, snag_id=row_id)
    return result.version, result.archived_at


KINDS: tuple[RecordKind, ...] = (
    "activity",
    "progress",
    "diary",
    "ehs",
    "template",
    "inspection",
    "snag",
)


@pytest.mark.parametrize("kind", KINDS)
async def test_archive_commits_once_with_version_and_valid_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession], *, kind: RecordKind
) -> None:
    async with session_factory() as session:
        ids = await _seed_records(session)
        actor_id = await session.scalar(
            text("SELECT created_by FROM construction.schedule_activities WHERE id = :id"),
            {"id": ids["activity"]},
        )
        assert actor_id is not None

        version, archived_at = await _archive(
            session, actor_id=actor_id, kind=kind, row_id=ids[kind]
        )
        await session.commit()
        second_version, second_archived_at = await _archive(
            session, actor_id=actor_id, kind=kind, row_id=ids[kind]
        )
        await session.commit()

        state = (
            await session.execute(
                text(_state_query(kind)),
                {"id": ids[kind]},
            )
        ).one()
        chain = await _audit_chain(session)
        assert version == second_version == state.version == 2
        assert archived_at == second_archived_at == state.archived_at
        assert len(chain) == 1 and chain[0].action == "archive" and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state


@pytest.mark.parametrize("kind", KINDS)
async def test_archive_rollback_restores_row_and_audit(
    session_factory: async_sessionmaker[AsyncSession], *, kind: RecordKind
) -> None:
    async with session_factory() as session:
        ids = await _seed_records(session)
        actor_id = await session.scalar(
            text("SELECT created_by FROM construction.schedule_activities WHERE id = :id"),
            {"id": ids["activity"]},
        )
        assert actor_id is not None
        await _archive(session, actor_id=actor_id, kind=kind, row_id=ids[kind])
        await session.rollback()

        state = (
            await session.execute(
                text(_state_query(kind)),
                {"id": ids[kind]},
            )
        ).one()
        assert tuple(state) == (1, None)
        assert await _audit_chain(session) == []


@pytest.mark.parametrize(
    ("kind", "nonterminal_status"),
    [
        ("activity", "in_progress"),
        ("ehs", "open"),
        ("template", "active"),
        ("inspection", "scheduled"),
        ("snag", "rectified"),
    ],
)
async def test_nonterminal_lifecycle_record_cannot_be_archived(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    kind: RecordKind,
    nonterminal_status: str,
) -> None:
    async with session_factory() as session:
        ids = await _seed_records(session)
        actor_id = await session.scalar(
            text("SELECT created_by FROM construction.schedule_activities WHERE id = :id"),
            {"id": ids["activity"]},
        )
        assert actor_id is not None
        await session.execute(
            text(_status_update(kind)),
            {"status": nonterminal_status, "id": ids[kind]},
        )
        await session.commit()

        with pytest.raises(ConstructionConflictError, match=r"only a|only an"):
            await _archive(session, actor_id=actor_id, kind=kind, row_id=ids[kind])
        await session.rollback()
        assert await _audit_chain(session) == []
