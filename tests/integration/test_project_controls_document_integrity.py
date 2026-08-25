"""Phase 6 controlled-document evidence integrity against PostgreSQL."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.documents.service import DocumentsService
from atlas.modules.project_controls.contracts import ProjectControlsConflictError
from atlas.modules.project_controls.schemas import BimImportCreate, IssuanceCreate, ReceiptCreate
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


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_scope(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
    project_id, other_project_id, material_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Phase 6 Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"phase6-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Phase 6 Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Phase 6 Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project_id, :entity_id, 'Synthetic Phase 6 Project', :project_code, "
            "'active', 1), "
            "(:other_project_id, :entity_id, 'Synthetic Other Project', :other_code, "
            "'active', 1)"
        ),
        {
            "project_id": project_id,
            "other_project_id": other_project_id,
            "entity_id": entity_id,
            "project_code": f"SYN-P6-{project_id}",
            "other_code": f"SYN-P6-{other_project_id}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO inventory.materials "
            "(id, name, unit_of_measure, created_by, updated_by, version) "
            "VALUES (:id, :name, 'synthetic-unit', :actor_id, :actor_id, 1)"
        ),
        {"id": material_id, "name": f"Synthetic material {material_id}", "actor_id": actor_id},
    )
    await session.commit()
    return actor_id, project_id, other_project_id, material_id


async def _seed_document(
    session: AsyncSession,
    *,
    project_id: UUID,
    revision_status: str,
    archived: bool = False,
) -> UUID:
    document_id, revision_id = uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, version, archived_at) "
            "VALUES (:id, :project_id, 'phase6_evidence', 'restricted', 'uploaded', 1, "
            "CASE WHEN :archived THEN now() ELSE NULL END)"
        ),
        {"id": document_id, "project_id": project_id, "archived": archived},
    )
    await session.execute(
        text(
            "INSERT INTO documents.document_versions "
            "(id, document_id, revision_code, object_storage_key, checksum_sha256, status) "
            "VALUES (:id, :document_id, 'SYN-R1', :storage_key, :checksum, :status)"
        ),
        {
            "id": revision_id,
            "document_id": document_id,
            "storage_key": f"synthetic/phase6/{revision_id}",
            "checksum": "c" * 64,
            "status": revision_status,
        },
    )
    await session.commit()
    return document_id


async def _seed_receipt(
    session: AsyncSession, *, actor_id: UUID, project_id: UUID, material_id: UUID
) -> UUID:
    receipt_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO inventory.material_receipts "
            "(id, project_id, material_id, quantity_received, received_date, status, "
            "created_by, updated_by, version) "
            "VALUES (:id, :project_id, :material_id, 100, '2026-08-24', 'received', "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": receipt_id,
            "project_id": project_id,
            "material_id": material_id,
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return receipt_id


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


async def _audit_count(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0)


def _service() -> ProjectControlsService:
    identity = AllowAllIdentity()
    return ProjectControlsService(identity, DocumentsService(identity))


@pytest.mark.parametrize(
    ("same_project", "revision_status", "archived"),
    [
        (False, "virus_scanned", False),
        (True, "draft", False),
        (True, "approved", True),
    ],
)
async def test_bim_import_refuses_uncontrolled_source_without_mutation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    same_project: bool,
    revision_status: str,
    archived: bool,
) -> None:
    async with session_factory() as session:
        actor_id, project_id, other_project_id, _ = await _seed_scope(session)
        document_id = await _seed_document(
            session,
            project_id=project_id if same_project else other_project_id,
            revision_status=revision_status,
            archived=archived,
        )
        audit_count = await _audit_count(session)
        with pytest.raises(ProjectControlsConflictError, match="BIM import"):
            await _service().register_bim_import(
                session,
                actor_user_id=actor_id,
                data=BimImportCreate(project_id, document_id),
            )
        await session.rollback()
        count = await session.scalar(
            text(
                "SELECT count(*) FROM design.bim_imports "
                "WHERE project_id = :project_id AND source_document_id = :document_id"
            ),
            {"project_id": project_id, "document_id": document_id},
        )
        assert count == 0
        assert await _audit_count(session) == audit_count


async def test_bim_import_accepts_malware_cleared_project_document_atomically(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, _ = await _seed_scope(session)
        document_id = await _seed_document(
            session, project_id=project_id, revision_status="virus_scanned"
        )
        result = await _service().register_bim_import(
            session,
            actor_user_id=actor_id,
            data=BimImportCreate(project_id, document_id),
        )
        await session.commit()
        chain = await _audit_chain(session)
        assert result.source_document_id == document_id and result.status == "received"
        assert len(chain) == 1 and verify_chain(chain) == 1


@pytest.mark.parametrize(
    ("same_project", "revision_status"), [(False, "approved"), (True, "draft")]
)
async def test_receipt_refuses_unapproved_or_cross_project_certificate(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    same_project: bool,
    revision_status: str,
) -> None:
    async with session_factory() as session:
        actor_id, project_id, other_project_id, material_id = await _seed_scope(session)
        document_id = await _seed_document(
            session,
            project_id=project_id if same_project else other_project_id,
            revision_status=revision_status,
        )
        audit_count = await _audit_count(session)
        with pytest.raises(ProjectControlsConflictError, match="certificate"):
            await _service().record_receipt(
                session,
                actor_user_id=actor_id,
                data=ReceiptCreate(
                    project_id,
                    material_id,
                    Decimal("12"),
                    date(2026, 8, 24),
                    certificate_document_id=document_id,
                ),
            )
        await session.rollback()
        count = await session.scalar(
            text(
                "SELECT count(*) FROM inventory.material_receipts "
                "WHERE project_id = :project_id AND material_id = :material_id"
            ),
            {"project_id": project_id, "material_id": material_id},
        )
        assert count == 0
        assert await _audit_count(session) == audit_count


async def test_receipt_accepts_approved_certificate_with_valid_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, material_id = await _seed_scope(session)
        document_id = await _seed_document(
            session, project_id=project_id, revision_status="approved"
        )
        result = await _service().record_receipt(
            session,
            actor_user_id=actor_id,
            data=ReceiptCreate(
                project_id,
                material_id,
                Decimal("12"),
                date(2026, 8, 24),
                batch_reference="SYNTHETIC PRIVATE BATCH",
                certificate_document_id=document_id,
            ),
        )
        await session.commit()
        chain = await _audit_chain(session)
        assert result.certificate_document_id == document_id
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE BATCH" not in chain[0].after_state


@pytest.mark.parametrize(("same_project", "revision_status"), [(False, "issued"), (True, "draft")])
async def test_issuance_refuses_unapproved_or_cross_project_evidence(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    same_project: bool,
    revision_status: str,
) -> None:
    async with session_factory() as session:
        actor_id, project_id, other_project_id, material_id = await _seed_scope(session)
        receipt_id = await _seed_receipt(
            session, actor_id=actor_id, project_id=project_id, material_id=material_id
        )
        document_id = await _seed_document(
            session,
            project_id=project_id if same_project else other_project_id,
            revision_status=revision_status,
        )
        audit_count = await _audit_count(session)
        with pytest.raises(ProjectControlsConflictError, match="issuance"):
            await _service().issue_material(
                session,
                actor_user_id=actor_id,
                receipt_id=receipt_id,
                data=IssuanceCreate(
                    Decimal("5"), date(2026, 8, 24), evidence_document_id=document_id
                ),
            )
        await session.rollback()
        count = await session.scalar(
            text(
                "SELECT count(*) FROM inventory.material_issuances "
                "WHERE material_receipt_id = :receipt_id"
            ),
            {"receipt_id": receipt_id},
        )
        assert count == 0
        assert await _audit_count(session) == audit_count


async def test_issuance_accepts_approved_evidence_with_valid_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, material_id = await _seed_scope(session)
        receipt_id = await _seed_receipt(
            session, actor_id=actor_id, project_id=project_id, material_id=material_id
        )
        document_id = await _seed_document(session, project_id=project_id, revision_status="issued")
        result = await _service().issue_material(
            session,
            actor_user_id=actor_id,
            receipt_id=receipt_id,
            data=IssuanceCreate(
                Decimal("5"),
                date(2026, 8, 24),
                issued_to="SYNTHETIC PRIVATE RECIPIENT",
                evidence_document_id=document_id,
            ),
        )
        await session.commit()
        chain = await _audit_chain(session)
        assert result.evidence_document_id == document_id
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE RECIPIENT" not in chain[0].after_state
