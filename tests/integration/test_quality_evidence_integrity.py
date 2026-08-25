"""Phase 5 inspection and snag evidence integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.schemas import InspectionCompletion, SnagCreate
from atlas.modules.construction.service import ConstructionService
from atlas.modules.documents.service import DocumentsService
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


class InspectionLockProbeIdentity(AllowAllIdentity):
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


async def _seed_inspection(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
    project_id, other_project_id, inspection_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Inspector', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"inspector-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Quality Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Quality Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project_id, :entity_id, 'Synthetic Quality Project', :project_code, "
            "'active', 1), "
            "(:other_project_id, :entity_id, 'Synthetic Other Project', :other_code, "
            "'active', 1)"
        ),
        {
            "project_id": project_id,
            "other_project_id": other_project_id,
            "entity_id": entity_id,
            "project_code": f"SYN-QA-{project_id}",
            "other_code": f"SYN-QA-{other_project_id}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO quality.inspections "
            "(id, project_id, inspector_id, result, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, :actor_id, 'pending', 'scheduled', "
            ":actor_id, :actor_id, 1)"
        ),
        {"id": inspection_id, "project_id": project_id, "actor_id": actor_id},
    )
    await session.commit()
    return actor_id, project_id, other_project_id, inspection_id


async def _seed_evidence(
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
            "VALUES (:id, :project_id, 'quality_evidence', 'restricted', 'uploaded', 1, "
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
            "storage_key": f"synthetic/quality/{revision_id}",
            "checksum": "b" * 64,
            "status": revision_status,
        },
    )
    await session.commit()
    return document_id


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
    return ConstructionService(identity, DocumentsService(AllowAllIdentity()))


@pytest.mark.parametrize(
    ("same_project", "revision_status", "archived"),
    [
        (False, "virus_scanned", False),
        (True, "draft", False),
        (True, "quarantined", False),
        (True, "approved", True),
    ],
)
async def test_inspection_refuses_uncontrolled_evidence_without_state_change(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    same_project: bool,
    revision_status: str,
    archived: bool,
) -> None:
    async with session_factory() as session:
        actor_id, project_id, other_project_id, inspection_id = await _seed_inspection(session)
        document_id = await _seed_evidence(
            session,
            project_id=project_id if same_project else other_project_id,
            revision_status=revision_status,
            archived=archived,
        )
        with pytest.raises(ConstructionConflictError, match="evidence"):
            await _service(AllowAllIdentity()).complete_inspection(
                session,
                actor_user_id=actor_id,
                inspection_id=inspection_id,
                data=InspectionCompletion(
                    "pass", "SYNTHETIC PRIVATE INSPECTION NOTES", (document_id,)
                ),
            )
        await session.rollback()
        state = (
            await session.execute(
                text(
                    "SELECT result, status, notes, version FROM quality.inspections WHERE id = :id"
                ),
                {"id": inspection_id},
            )
        ).one()
        assert tuple(state) == ("pending", "scheduled", None, 1)
        assert await _audit_chain(session) == []


async def test_inspection_completion_commits_evidence_and_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, inspection_id = await _seed_inspection(session)
        document_id = await _seed_evidence(
            session, project_id=project_id, revision_status="virus_scanned"
        )
        result = await _service(AllowAllIdentity()).complete_inspection(
            session,
            actor_user_id=actor_id,
            inspection_id=inspection_id,
            data=InspectionCompletion(
                "fail", "SYNTHETIC PRIVATE INSPECTION NOTES", (document_id, document_id)
            ),
        )
        await session.commit()

        evidence_count = await session.scalar(
            text("SELECT count(*) FROM quality.inspection_evidence WHERE inspection_id = :id"),
            {"id": inspection_id},
        )
        chain = await _audit_chain(session)
        assert result.status == "completed" and result.version == 2
        assert evidence_count == 1
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state


async def test_inspection_completion_rollback_removes_state_evidence_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, inspection_id = await _seed_inspection(session)
        document_id = await _seed_evidence(
            session, project_id=project_id, revision_status="approved"
        )
        await _service(AllowAllIdentity()).complete_inspection(
            session,
            actor_user_id=actor_id,
            inspection_id=inspection_id,
            data=InspectionCompletion("pass", None, (document_id,)),
        )
        await session.rollback()

        state = (
            await session.execute(
                text("SELECT result, status, version FROM quality.inspections WHERE id = :id"),
                {"id": inspection_id},
            )
        ).one()
        evidence_count = await session.scalar(
            text("SELECT count(*) FROM quality.inspection_evidence WHERE inspection_id = :id"),
            {"id": inspection_id},
        )
        assert tuple(state) == ("pending", "scheduled", 1)
        assert evidence_count == 0
        assert await _audit_chain(session) == []


async def test_concurrent_inspection_completion_serializes_final_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, _, _, inspection_id = await _seed_inspection(seed)
    identity = InspectionLockProbeIdentity()

    async def complete(result: str) -> str:
        async with session_factory() as session:
            try:
                await _service(identity).complete_inspection(
                    session,
                    actor_user_id=actor_id,
                    inspection_id=inspection_id,
                    data=InspectionCompletion(result, None, ()),
                )
                await session.commit()
                return "completed"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(complete("pass"))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(complete("fail"))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["completed", "conflict"]

    async with session_factory() as session:
        state = (
            await session.execute(
                text("SELECT result, status, version FROM quality.inspections WHERE id = :id"),
                {"id": inspection_id},
            )
        ).one()
        assert tuple(state) == ("pass", "completed", 2)
        assert len(await _audit_chain(session)) == 1


@pytest.mark.parametrize("same_project", [False, True])
async def test_snag_refuses_cross_project_or_draft_evidence(
    session_factory: async_sessionmaker[AsyncSession], *, same_project: bool
) -> None:
    async with session_factory() as session:
        actor_id, project_id, other_project_id, _ = await _seed_inspection(session)
        document_id = await _seed_evidence(
            session,
            project_id=project_id if same_project else other_project_id,
            revision_status="draft" if same_project else "virus_scanned",
        )
        with pytest.raises(ConstructionConflictError, match="evidence"):
            await _service(AllowAllIdentity()).create_snag(
                session,
                actor_user_id=actor_id,
                data=SnagCreate(
                    project_id=project_id,
                    description="SYNTHETIC PRIVATE SNAG DESCRIPTION",
                    severity="major",
                    evidence_document_id=document_id,
                ),
            )
        await session.rollback()
        snag_count = await session.scalar(
            text("SELECT count(*) FROM quality.snag_items WHERE project_id = :project_id"),
            {"project_id": project_id},
        )
        assert snag_count == 0
        assert await _audit_chain(session) == []


async def test_snag_commits_controlled_evidence_with_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id, _, _ = await _seed_inspection(session)
        document_id = await _seed_evidence(
            session, project_id=project_id, revision_status="under_review"
        )
        snag = await _service(AllowAllIdentity()).create_snag(
            session,
            actor_user_id=actor_id,
            data=SnagCreate(
                project_id=project_id,
                description="SYNTHETIC PRIVATE SNAG DESCRIPTION",
                severity="major",
                evidence_document_id=document_id,
            ),
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert snag.evidence_document_id == document_id
        assert len(chain) == 1 and verify_chain(chain) == 1
        assert chain[0].after_state is not None
        assert "SYNTHETIC PRIVATE" not in chain[0].after_state
