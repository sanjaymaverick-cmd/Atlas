"""Database-enforced Phase 6 project and receipt scope invariants."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _reject(session: AsyncSession, statement: str, values: dict[str, object]) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(text(statement), values)


async def test_database_rejects_cross_scope_phase6_references(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
        project_a, project_b = uuid4(), uuid4()
        document_a, document_b = uuid4(), uuid4()
        import_a, import_b, object_a = uuid4(), uuid4(), uuid4()
        cost_code_a, material_a, material_b, receipt_a = uuid4(), uuid4(), uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO identity.users (id, full_name, email, status, version) "
                "VALUES (:id, 'Synthetic Scope Actor', :email, 'active', 1)"
            ),
            {"id": actor_id, "email": f"phase6-scope-{actor_id}@example.invalid"},
        )
        await session.execute(
            text(
                "INSERT INTO organization.business_groups (id, name, status, version) "
                "VALUES (:id, 'Synthetic Scope Group', 'active', 1)"
            ),
            {"id": group_id},
        )
        await session.execute(
            text(
                "INSERT INTO organization.legal_entities "
                "(id, business_group_id, name, status, version) "
                "VALUES (:id, :group_id, 'Synthetic Scope Entity', 'active', 1)"
            ),
            {"id": entity_id, "group_id": group_id},
        )
        await session.execute(
            text(
                "INSERT INTO organization.projects "
                "(id, legal_entity_id, name, code, status, version) VALUES "
                "(:a, :entity, 'Synthetic Scope A', :code_a, 'active', 1), "
                "(:b, :entity, 'Synthetic Scope B', :code_b, 'active', 1)"
            ),
            {
                "a": project_a,
                "b": project_b,
                "entity": entity_id,
                "code_a": f"SYN-P6-A-{project_a}",
                "code_b": f"SYN-P6-B-{project_b}",
            },
        )
        await session.execute(
            text(
                "INSERT INTO documents.documents "
                "(id, project_id, document_type, classification, status, version) VALUES "
                "(:a, :project_a, 'phase6', 'restricted', 'approved', 1), "
                "(:b, :project_b, 'phase6', 'restricted', 'approved', 1)"
            ),
            {
                "a": document_a,
                "b": document_b,
                "project_a": project_a,
                "project_b": project_b,
            },
        )
        await session.execute(
            text(
                "INSERT INTO design.bim_imports "
                "(id, project_id, source_file_reference, source_document_id, import_status, "
                "created_by, updated_by, version) VALUES "
                "(:a, :project_a, :source_a, :document_a, 'validated', :actor, :actor, 1), "
                "(:b, :project_b, :source_b, :document_b, 'validated', :actor, :actor, 1)"
            ),
            {
                "a": import_a,
                "b": import_b,
                "project_a": project_a,
                "project_b": project_b,
                "source_a": str(document_a),
                "source_b": str(document_b),
                "document_a": document_a,
                "document_b": document_b,
                "actor": actor_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO design.bim_objects "
                "(id, bim_import_id, ifc_guid, object_type, project_id, created_by) "
                "VALUES (:id, :import_id, 'SYN-GUID-A', 'material', :project_id, :actor)"
            ),
            {
                "id": object_a,
                "import_id": import_a,
                "project_id": project_a,
                "actor": actor_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO quantities.cost_codes "
                "(id, project_id, code, wbs_level, created_by, updated_by, version) "
                "VALUES (:id, :project_id, :code, 1, :actor, :actor, 1)"
            ),
            {
                "id": cost_code_a,
                "project_id": project_a,
                "code": f"SYN-WBS-{cost_code_a}",
                "actor": actor_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO inventory.materials "
                "(id, name, unit_of_measure, created_by, updated_by, version) VALUES "
                "(:a, :name_a, 'unit', :actor, :actor, 1), "
                "(:b, :name_b, 'unit', :actor, :actor, 1)"
            ),
            {
                "a": material_a,
                "b": material_b,
                "name_a": f"Synthetic A {material_a}",
                "name_b": f"Synthetic B {material_b}",
                "actor": actor_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO inventory.material_receipts "
                "(id, project_id, material_id, quantity_received, received_date, status, "
                "created_by, updated_by, version) "
                "VALUES (:id, :project_id, :material_id, 10, '2026-08-24', 'received', "
                ":actor, :actor, 1)"
            ),
            {
                "id": receipt_a,
                "project_id": project_a,
                "material_id": material_a,
                "actor": actor_id,
            },
        )
        await session.commit()

        await _reject(
            session,
            "INSERT INTO design.bim_imports "
            "(id, project_id, source_file_reference, source_document_id, import_status, version) "
            "VALUES (:id, :project, :source, :document, 'received', 1)",
            {
                "id": uuid4(),
                "project": project_b,
                "source": str(document_a),
                "document": document_a,
            },
        )
        await _reject(
            session,
            "INSERT INTO design.bim_objects "
            "(id, bim_import_id, ifc_guid, object_type, project_id) "
            "VALUES (:id, :import_id, :guid, 'material', :project)",
            {"id": uuid4(), "import_id": import_a, "guid": f"SYN-{uuid4()}", "project": project_b},
        )
        await _reject(
            session,
            "INSERT INTO quantities.quantity_items "
            "(id, project_id, cost_code_id, calculated_quantity, tolerance_pct, status, version) "
            "VALUES (:id, :project, :cost_code, 1, 2, 'calculated', 1)",
            {"id": uuid4(), "project": project_b, "cost_code": cost_code_a},
        )
        await _reject(
            session,
            "INSERT INTO quantities.quantity_items "
            "(id, project_id, bim_object_id, calculated_quantity, tolerance_pct, status, version) "
            "VALUES (:id, :project, :bim_object, 1, 2, 'calculated', 1)",
            {"id": uuid4(), "project": project_b, "bim_object": object_a},
        )
        await _reject(
            session,
            "INSERT INTO inventory.material_receipts "
            "(id, project_id, material_id, quantity_received, certificate_document_id, "
            "received_date, status, version) "
            "VALUES (:id, :project, :material, 1, :document, '2026-08-24', 'received', 1)",
            {
                "id": uuid4(),
                "project": project_b,
                "material": material_b,
                "document": document_a,
            },
        )
        await _reject(
            session,
            "INSERT INTO inventory.material_issuances "
            "(id, project_id, material_id, material_receipt_id, quantity_issued, issued_date, "
            "version) VALUES (:id, :project, :material, :receipt, 1, '2026-08-24', 1)",
            {
                "id": uuid4(),
                "project": project_b,
                "material": material_b,
                "receipt": receipt_a,
            },
        )
        await _reject(
            session,
            "INSERT INTO inventory.material_issuances "
            "(id, project_id, material_id, material_receipt_id, quantity_issued, issued_date, "
            "evidence_document_id, version) "
            "VALUES (:id, :project, :material, :receipt, 1, '2026-08-24', :document, 1)",
            {
                "id": uuid4(),
                "project": project_a,
                "material": material_a,
                "receipt": receipt_a,
                "document": document_b,
            },
        )
