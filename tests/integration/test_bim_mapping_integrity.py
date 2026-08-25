"""Structured BIM object import integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.organization.service import OrganizationService
from atlas.modules.project_controls.contracts import ProjectControlsConflictError
from atlas.modules.project_controls.schemas import BimObjectCreate
from atlas.modules.project_controls.service import ProjectControlsService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = pytest.mark.integration


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


class ImportLockProbeIdentity(AllowAllIdentity):
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


async def _seed(
    session: AsyncSession,
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
    actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
    project_id, other_project_id = uuid4(), uuid4()
    document_id, import_id, material_id = uuid4(), uuid4(), uuid4()
    other_building_id, other_floor_id, other_unit_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic BIM Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"bim-map-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic BIM Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group, 'Synthetic BIM Entity', 'active', 1)"
        ),
        {"id": entity_id, "group": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project, :entity, 'Synthetic BIM Project', :code, 'active', 1), "
            "(:other, :entity, 'Synthetic Other BIM Project', :other_code, 'active', 1)"
        ),
        {
            "project": project_id,
            "other": other_project_id,
            "entity": entity_id,
            "code": f"SYN-BIM-{project_id}",
            "other_code": f"SYN-BIM-{other_project_id}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO organization.buildings (id, project_id, name, code, status) "
            "VALUES (:id, :project, 'Synthetic Other Building', 'SYN-B', 'active')"
        ),
        {"id": other_building_id, "project": other_project_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.floors (id, building_id, floor_number, name, status) "
            "VALUES (:id, :building, 1, 'Synthetic Floor', 'active')"
        ),
        {"id": other_floor_id, "building": other_building_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.units (id, floor_id, unit_number, status) "
            "VALUES (:id, :floor, 'SYN-U1', 'available')"
        ),
        {"id": other_unit_id, "floor": other_floor_id},
    )
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, version) "
            "VALUES (:id, :project, 'bim', 'restricted', 'approved', 1)"
        ),
        {"id": document_id, "project": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO design.bim_imports "
            "(id, project_id, source_file_reference, source_document_id, import_status, "
            "created_by, updated_by, version) "
            "VALUES (:id, :project, :source, :document, 'validated', :actor, :actor, 1)"
        ),
        {
            "id": import_id,
            "project": project_id,
            "source": str(document_id),
            "document": document_id,
            "actor": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO inventory.materials "
            "(id, name, unit_of_measure, created_by, updated_by, version) "
            "VALUES (:id, :name, 'unit', :actor, :actor, 1)"
        ),
        {"id": material_id, "name": f"Synthetic BIM Material {material_id}", "actor": actor_id},
    )
    await session.commit()
    return actor_id, project_id, import_id, material_id, other_unit_id, other_project_id


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


def _service(identity: AllowAllIdentity) -> ProjectControlsService:
    return ProjectControlsService(identity, organization=OrganizationService(identity))


@pytest.mark.parametrize("invalid_kind", ["location", "material", "missing_material_mapping"])
async def test_bim_mapping_refuses_invalid_references_without_mutation(
    session_factory: async_sessionmaker[AsyncSession], invalid_kind: str
) -> None:
    async with session_factory() as session:
        actor_id, _, import_id, material_id, other_unit_id, _ = await _seed(session)
        if invalid_kind == "location":
            value = BimObjectCreate("SYN-INVALID-LOCATION", "unit", unit_id=other_unit_id)
        elif invalid_kind == "material":
            value = BimObjectCreate("SYN-INVALID-MATERIAL", "material", material_id=uuid4())
        else:
            value = BimObjectCreate("SYN-MISSING-MATERIAL", "material")
        with pytest.raises(ProjectControlsConflictError):
            await _service(AllowAllIdentity()).import_bim_objects(
                session, actor_user_id=actor_id, import_id=import_id, objects=(value,)
            )
        await session.rollback()
        state = (
            await session.execute(
                text("SELECT import_status, version FROM design.bim_imports WHERE id = :id"),
                {"id": import_id},
            )
        ).one()
        object_count = await session.scalar(
            text("SELECT count(*) FROM design.bim_objects WHERE bim_import_id = :id"),
            {"id": import_id},
        )
        assert tuple(state) == ("validated", 1)
        assert object_count == 0
        assert all(event.entity_id != import_id for event in await _audit_chain(session))
        assert material_id is not None


async def test_bim_mapping_commits_objects_status_and_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, import_id, material_id, _, _ = await _seed(session)
        service = _service(AllowAllIdentity())
        result = await service.import_bim_objects(
            session,
            actor_user_id=actor_id,
            import_id=import_id,
            objects=(
                BimObjectCreate(
                    "SYN-MATERIAL-GUID",
                    "material",
                    room_reference="SYNTHETIC PRIVATE ROOM",
                    material_id=material_id,
                ),
                BimObjectCreate(
                    "SYN-WORK-GUID",
                    "work_package",
                    work_package="SYNTHETIC PRIVATE WORK PACKAGE",
                ),
            ),
        )
        await session.commit()
        listed = await service.list_bim_objects(
            session, actor_user_id=actor_id, import_id=import_id
        )
        chain = [event for event in await _audit_chain(session) if event.entity_id == import_id]
        assert result.status == "imported" and result.version == 2
        assert len(listed) == 2 and all(value.project_id == project_id for value in listed)
        assert len(chain) == 1 and verify_chain(await _audit_chain(session)) >= 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state


async def test_bim_mapping_rollback_removes_objects_status_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, import_id, _, _, _ = await _seed(session)
        audit_count = len(await _audit_chain(session))
        await _service(AllowAllIdentity()).import_bim_objects(
            session,
            actor_user_id=actor_id,
            import_id=import_id,
            objects=(BimObjectCreate("SYN-ROLLBACK-GUID", "work_package"),),
        )
        await session.rollback()
        state = (
            await session.execute(
                text("SELECT import_status, version FROM design.bim_imports WHERE id = :id"),
                {"id": import_id},
            )
        ).one()
        count = await session.scalar(
            text("SELECT count(*) FROM design.bim_objects WHERE bim_import_id = :id"),
            {"id": import_id},
        )
        assert tuple(state) == ("validated", 1)
        assert count == 0 and len(await _audit_chain(session)) == audit_count


async def test_validated_import_cannot_bypass_object_mapping(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, import_id, _, _, _ = await _seed(session)
        with pytest.raises(ProjectControlsConflictError, match="cannot move"):
            await _service(AllowAllIdentity()).transition_bim_import(
                session,
                actor_user_id=actor_id,
                import_id=import_id,
                target_status="imported",
            )
        await session.rollback()
        state = (
            await session.execute(
                text("SELECT import_status, version FROM design.bim_imports WHERE id = :id"),
                {"id": import_id},
            )
        ).one()
        assert tuple(state) == ("validated", 1)


async def test_concurrent_bim_mapping_allows_one_import_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed_session:
        actor_id, _, import_id, _, _, _ = await _seed(seed_session)
    identity = ImportLockProbeIdentity()
    service = _service(identity)

    async def run(session: AsyncSession, guid: str) -> object:
        result = await service.import_bim_objects(
            session,
            actor_user_id=actor_id,
            import_id=import_id,
            objects=(BimObjectCreate(guid, "work_package"),),
        )
        await session.commit()
        return result

    async with session_factory() as first_session, session_factory() as second_session:
        first = asyncio.create_task(run(first_session, "SYN-FIRST-GUID"))
        await asyncio.wait_for(identity.first_has_lock.wait(), timeout=2)
        second = asyncio.create_task(run(second_session, "SYN-SECOND-GUID"))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), timeout=0.2)
        identity.release_first.set()
        await asyncio.wait_for(first, timeout=2)
        with pytest.raises(ProjectControlsConflictError, match="validated import"):
            await asyncio.wait_for(second, timeout=2)
        await second_session.rollback()

    async with session_factory() as check_session:
        rows = (
            (
                await check_session.execute(
                    text(
                        "SELECT ifc_guid FROM design.bim_objects "
                        "WHERE bim_import_id = :id ORDER BY ifc_guid"
                    ),
                    {"id": import_id},
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["SYN-FIRST-GUID"]
