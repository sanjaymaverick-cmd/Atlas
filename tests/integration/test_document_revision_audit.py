"""Document revisions preserve history and share a transaction with audit events."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.documents.contracts import DocumentConflictError
from atlas.modules.documents.schemas import DocumentCreate, RevisionCreate
from atlas.modules.documents.service import DocumentsService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = pytest.mark.integration


class ScopedIdentity:
    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return project_id is not None


@pytest.fixture
async def document_session(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def seed_scope(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id = uuid4()
    group_id = uuid4()
    entity_id = uuid4()
    project_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Synthetic Document Actor', :email, false, 'active', 1)"
        ),
        {"id": actor_id, "email": f"document-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Project', :code, 'planning', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-{project_id}"},
    )
    await session.commit()
    return actor_id, project_id


async def audit_chain(session: AsyncSession) -> list[AuditRecord]:
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


async def test_document_revision_and_archive_are_versioned_and_audited(
    document_session: AsyncSession,
) -> None:
    actor_id, project_id = await seed_scope(document_session)
    service = DocumentsService(ScopedIdentity())  # type: ignore[arg-type]
    created = await service.create_document(
        document_session,
        actor_user_id=actor_id,
        data=DocumentCreate(
            project_id=project_id,
            discipline="architectural",
            drawing_number="SYN-A-001",
            document_type="drawing",
            classification="confidential",
        ),
    )
    first = await service.add_revision(
        document_session,
        actor_user_id=actor_id,
        document_id=created.id,
        data=RevisionCreate("A", "synthetic/document/revision-a", "a" * 64),
    )
    second = await service.add_revision(
        document_session,
        actor_user_id=actor_id,
        document_id=created.id,
        data=RevisionCreate("B", "synthetic/document/revision-b", "b" * 64),
    )
    archived = await service.archive_document(
        document_session, actor_user_id=actor_id, document_id=created.id
    )
    await document_session.commit()

    assert second.superseded_version_id == first.id
    assert archived.version == 4
    assert archived.archived_at is not None
    chain = await audit_chain(document_session)
    assert [record.action for record in chain] == [
        "create",
        "create_revision",
        "create_revision",
        "archive",
    ]
    assert verify_chain(chain) == 4


async def test_duplicate_revision_code_rolls_back_without_a_second_event(
    document_session: AsyncSession,
) -> None:
    actor_id, project_id = await seed_scope(document_session)
    service = DocumentsService(ScopedIdentity())  # type: ignore[arg-type]
    created = await service.create_document(
        document_session,
        actor_user_id=actor_id,
        data=DocumentCreate(project_id, None, None, "drawing"),
    )
    await service.add_revision(
        document_session,
        actor_user_id=actor_id,
        document_id=created.id,
        data=RevisionCreate("A", "synthetic/document/a", "a" * 64),
    )
    await document_session.commit()

    with pytest.raises(DocumentConflictError):
        await service.add_revision(
            document_session,
            actor_user_id=actor_id,
            document_id=created.id,
            data=RevisionCreate("A", "synthetic/document/duplicate", "b" * 64),
        )
    await document_session.rollback()
    assert [record.action for record in await audit_chain(document_session)] == [
        "create",
        "create_revision",
    ]
