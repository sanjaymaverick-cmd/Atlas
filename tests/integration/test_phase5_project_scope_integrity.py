"""Phase 5 project-scope references against canonical PostgreSQL."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.schemas import (
    EhsCreate,
    InspectionCreate,
    ScheduleCreate,
    SnagCreate,
)
from atlas.modules.construction.service import ConstructionService
from atlas.modules.organization.service import OrganizationService
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


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_scope(session: AsyncSession) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "actor",
            "group",
            "entity",
            "project",
            "other_project",
            "activity",
            "diary",
            "template",
            "global_template",
            "inspection",
            "building",
            "other_building",
            "floor",
            "unit",
        )
    }
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Scope Actor', :email, 'active', 1)"
        ),
        {"id": ids["actor"], "email": f"scope-{ids['actor']}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Scope Group', 'active', 1)"
        ),
        {"id": ids["group"]},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Scope Entity', 'active', 1)"
        ),
        {"id": ids["entity"], "group_id": ids["group"]},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project, :entity, 'Synthetic Scope Project', :project_code, 'active', 1), "
            "(:other_project, :entity, 'Synthetic Other Scope Project', :other_code, "
            "'active', 1)"
        ),
        {
            "project": ids["project"],
            "other_project": ids["other_project"],
            "entity": ids["entity"],
            "project_code": f"SYN-SCOPE-{ids['project']}",
            "other_code": f"SYN-SCOPE-{ids['other_project']}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(id, project_id, name, status, version) "
            "VALUES (:id, :project, 'Synthetic Scoped Activity', 'not_started', 1)"
        ),
        {"id": ids["activity"], "project": ids["project"]},
    )
    await session.execute(
        text(
            "INSERT INTO construction.site_diary_entries "
            "(id, project_id, entry_date, client_record_id, status, version) "
            "VALUES (:id, :project, :entry_date, :client_id, 'submitted', 1)"
        ),
        {
            "id": ids["diary"],
            "project": ids["project"],
            "entry_date": date(2026, 8, 23),
            "client_id": uuid4(),
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspection_templates "
            "(id, project_id, work_package, template_name, checklist, status, version) VALUES "
            "(:template, :project, 'synthetic', :project_name, '[]'::jsonb, 'active', 1), "
            "(:global_template, NULL, 'synthetic', :global_name, '[]'::jsonb, 'active', 1)"
        ),
        {
            "template": ids["template"],
            "global_template": ids["global_template"],
            "project": ids["project"],
            "project_name": f"Synthetic Scoped Template {ids['template']}",
            "global_name": f"Synthetic Global Template {ids['global_template']}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspections "
            "(id, project_id, result, status, version) "
            "VALUES (:id, :project, 'pending', 'scheduled', 1)"
        ),
        {"id": ids["inspection"], "project": ids["project"]},
    )
    await session.execute(
        text(
            "INSERT INTO organization.buildings (id, project_id, name, status) VALUES "
            "(:building, :project, 'Synthetic Building A', 'active'), "
            "(:other_building, :project, 'Synthetic Building B', 'active')"
        ),
        {
            "building": ids["building"],
            "other_building": ids["other_building"],
            "project": ids["project"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO organization.floors (id, building_id, floor_number, status) "
            "VALUES (:id, :building, 1, 'active')"
        ),
        {"id": ids["floor"], "building": ids["building"]},
    )
    await session.execute(
        text(
            "INSERT INTO organization.units (id, floor_id, unit_number, status) "
            "VALUES (:id, :floor, 'SYN-1', 'available')"
        ),
        {"id": ids["unit"], "floor": ids["floor"]},
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


def _service(identity: AllowAllIdentity) -> ConstructionService:
    return ConstructionService(identity, organization=OrganizationService(identity))


@pytest.mark.parametrize(
    "operation",
    ["predecessor", "diary", "template", "inspection", "location", "hierarchy"],
)
async def test_service_refuses_cross_project_or_inconsistent_references(
    session_factory: async_sessionmaker[AsyncSession], *, operation: str
) -> None:
    async with session_factory() as session:
        ids = await _seed_scope(session)
        service = _service(AllowAllIdentity())
        with pytest.raises(ConstructionConflictError, match=r"project|hierarchy"):
            if operation == "predecessor":
                await service.create_activity(
                    session,
                    actor_user_id=ids["actor"],
                    data=ScheduleCreate(
                        project_id=ids["other_project"],
                        name="Synthetic Invalid Activity",
                        predecessor_activity_id=ids["activity"],
                    ),
                )
            elif operation == "diary":
                await service.create_ehs_incident(
                    session,
                    actor_user_id=ids["actor"],
                    data=EhsCreate(
                        project_id=ids["other_project"],
                        incident_date=date(2026, 8, 23),
                        severity="minor",
                        site_diary_entry_id=ids["diary"],
                    ),
                )
            elif operation == "template":
                await service.schedule_inspection(
                    session,
                    actor_user_id=ids["actor"],
                    data=InspectionCreate(
                        project_id=ids["other_project"],
                        template_id=ids["template"],
                        inspector_id=None,
                    ),
                )
            elif operation == "inspection":
                await service.create_snag(
                    session,
                    actor_user_id=ids["actor"],
                    data=SnagCreate(
                        project_id=ids["other_project"],
                        description="SYNTHETIC PRIVATE INVALID SNAG",
                        severity="major",
                        inspection_id=ids["inspection"],
                    ),
                )
            elif operation == "location":
                await service.schedule_inspection(
                    session,
                    actor_user_id=ids["actor"],
                    data=InspectionCreate(
                        project_id=ids["other_project"],
                        template_id=ids["global_template"],
                        inspector_id=None,
                        unit_id=ids["unit"],
                    ),
                )
            else:
                await service.create_snag(
                    session,
                    actor_user_id=ids["actor"],
                    data=SnagCreate(
                        project_id=ids["project"],
                        description="SYNTHETIC PRIVATE INVALID HIERARCHY",
                        severity="major",
                        building_id=ids["other_building"],
                        unit_id=ids["unit"],
                    ),
                )
        await session.rollback()
        assert await _audit_chain(session) == []


async def test_valid_global_template_and_location_commit_with_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        ids = await _seed_scope(session)
        inspection = await _service(AllowAllIdentity()).schedule_inspection(
            session,
            actor_user_id=ids["actor"],
            data=InspectionCreate(
                project_id=ids["project"],
                template_id=ids["global_template"],
                inspector_id=ids["actor"],
                building_id=ids["building"],
                floor_id=ids["floor"],
                unit_id=ids["unit"],
            ),
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert inspection.project_id == ids["project"]
        assert len(chain) == 1 and verify_chain(chain) == 1


def _sync_seed(db: Any) -> dict[str, UUID]:
    ids = {name: uuid4() for name in ("group", "entity", "project", "other_project")}
    db.execute(
        "INSERT INTO organization.business_groups (id, name, status, version) "
        "VALUES (%(id)s, 'Synthetic DB Scope Group', 'active', 1)",
        {"id": ids["group"]},
    )
    db.execute(
        "INSERT INTO organization.legal_entities "
        "(id, business_group_id, name, status, version) "
        "VALUES (%(id)s, %(group)s, 'Synthetic DB Scope Entity', 'active', 1)",
        {"id": ids["entity"], "group": ids["group"]},
    )
    db.execute(
        "INSERT INTO organization.projects "
        "(id, legal_entity_id, name, code, status, version) VALUES "
        "(%(project)s, %(entity)s, 'Synthetic DB Project', %(project_code)s, 'active', 1), "
        "(%(other)s, %(entity)s, 'Synthetic DB Other Project', %(other_code)s, 'active', 1)",
        {
            "project": ids["project"],
            "other": ids["other_project"],
            "entity": ids["entity"],
            "project_code": f"SYN-DB-{ids['project']}",
            "other_code": f"SYN-DB-{ids['other_project']}",
        },
    )
    return ids


def test_database_rejects_all_cross_project_phase5_references(db: Any) -> None:
    ids = _sync_seed(db)
    activity_id, diary_id, inspection_id = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO construction.schedule_activities (id, project_id, name, status, version) "
        "VALUES (%(id)s, %(project)s, 'Synthetic DB Activity', 'not_started', 1)",
        {"id": activity_id, "project": ids["project"]},
    )
    db.execute(
        "INSERT INTO construction.site_diary_entries "
        "(id, project_id, entry_date, client_record_id, status, version) "
        "VALUES (%(id)s, %(project)s, %(entry_date)s, %(client)s, 'submitted', 1)",
        {
            "id": diary_id,
            "project": ids["project"],
            "entry_date": date(2026, 8, 23),
            "client": uuid4(),
        },
    )
    db.execute(
        "INSERT INTO quality.inspections (id, project_id, result, status, version) "
        "VALUES (%(id)s, %(project)s, 'pending', 'scheduled', 1)",
        {"id": inspection_id, "project": ids["project"]},
    )

    attempts = [
        (
            "INSERT INTO construction.schedule_activities "
            "(project_id, name, predecessor_activity_id, status, version) "
            "VALUES (%(project)s, 'Synthetic Invalid Predecessor', %(reference)s, "
            "'not_started', 1)",
            activity_id,
            "fk_schedule_predecessor_project",
        ),
        (
            "INSERT INTO construction.ehs_incidents "
            "(project_id, site_diary_entry_id, incident_date, severity, status, version) "
            "VALUES (%(project)s, %(reference)s, %(incident_date)s, 'minor', 'open', 1)",
            diary_id,
            "fk_ehs_diary_project",
        ),
        (
            "INSERT INTO construction.progress_updates "
            "(project_id, schedule_activity_id, progress_date, percent_complete, version) "
            "VALUES (%(project)s, %(reference)s, %(progress_date)s, 10, 1)",
            activity_id,
            "fk_progress_activity_project",
        ),
        (
            "INSERT INTO quality.snag_items "
            "(project_id, inspection_id, description, severity, status, version) "
            "VALUES (%(project)s, %(reference)s, 'Synthetic Invalid Snag', "
            "'major', 'open', 1)",
            inspection_id,
            "fk_snag_inspection_project",
        ),
    ]
    for statement, reference_id, constraint_name in attempts:
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
            db.execute(
                statement,
                {
                    "project": ids["other_project"],
                    "reference": reference_id,
                    "incident_date": date(2026, 8, 23),
                    "progress_date": date(2026, 8, 23),
                },
            )
        assert violation.value.diag.constraint_name == constraint_name
