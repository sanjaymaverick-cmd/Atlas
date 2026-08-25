"""Database-free tests for Phase 2 document invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.documents import service as service_module
from atlas.modules.documents.contracts import (
    DocumentConflictError,
    DocumentNotAuthorisedError,
)
from atlas.modules.documents.models import Document, DocumentVersion
from atlas.modules.documents.schemas import DocumentCreate, RevisionCreate
from atlas.modules.documents.service import DocumentsService
from atlas.modules.documents.storage import LocalDocumentStorage
from atlas.modules.identity.contracts import IdentityContract

pytestmark = pytest.mark.unit


class IdentityStub:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.permissions: list[tuple[str, UUID]] = []

    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        assert project_id is not None
        self.permissions.append((permission_code, project_id))
        return self.allowed


class SessionStub:
    def __init__(self, *, document: Document | None = None) -> None:
        self.document = document
        self.latest: DocumentVersion | None = None
        self.added: list[object] = []
        self.flushes = 0

    async def get(self, model: object, key: UUID) -> Document | None:
        return self.document

    async def scalar(self, statement: object) -> DocumentVersion | None:
        return self.latest

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


async def ignore_audit(*args: object, **kwargs: object) -> None:
    return None


def document(*, archived: bool = False) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=uuid4(),
        project_id=uuid4(),
        building_id=None,
        floor_id=None,
        unit_id=None,
        discipline="architectural",
        drawing_number="SYN-A-001",
        document_type="drawing",
        classification="confidential",
        status="archived" if archived else "uploaded",
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=1,
        archived_at=now if archived else None,
    )


async def test_create_document_is_project_scoped_versioned_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityStub()
    service = DocumentsService(cast(IdentityContract, identity))
    session = SessionStub()
    actor_id = uuid4()
    project_id = uuid4()
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    result = await service.create_document(
        cast(AsyncSession, session),
        actor_user_id=actor_id,
        data=DocumentCreate(
            project_id=project_id,
            discipline="architectural",
            drawing_number="SYN-A-001",
            document_type="drawing",
            classification="confidential",
        ),
    )
    assert result.project_id == project_id
    assert result.version == 1
    assert identity.permissions == [("document.create", project_id)]
    assert events[0]["action"] == "create"
    assert session.flushes == 1


async def test_new_revision_is_immutable_and_links_to_previous_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityStub()
    service = DocumentsService(cast(IdentityContract, identity))
    row = document()
    session = SessionStub(document=row)
    previous = DocumentVersion(
        id=uuid4(),
        document_id=row.id,
        revision_code="A",
        issue_purpose=None,
        issue_date=None,
        author_id=uuid4(),
        reviewer_id=None,
        approver_id=None,
        superseded_version_id=None,
        related_change_request_id=None,
        object_storage_key="synthetic/a",
        checksum_sha256="a" * 64,
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.latest = previous
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    result = await service.add_revision(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        document_id=row.id,
        data=RevisionCreate(
            revision_code="B",
            object_storage_key="synthetic/b",
            checksum_sha256="b" * 64,
        ),
    )
    assert result.superseded_version_id == previous.id
    assert result.revision_code == "B"
    assert row.version == 2
    assert len(session.added) == 1


async def test_archived_document_refuses_new_revisions(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DocumentsService(cast(IdentityContract, IdentityStub()))
    row = document(archived=True)
    session = SessionStub(document=row)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    with pytest.raises(DocumentConflictError):
        await service.add_revision(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            document_id=row.id,
            data=RevisionCreate("B", "synthetic/b", "b" * 64),
        )
    assert session.added == []


async def test_permission_refusal_happens_before_mutation() -> None:
    service = DocumentsService(cast(IdentityContract, IdentityStub(allowed=False)))
    session = SessionStub()
    with pytest.raises(DocumentNotAuthorisedError):
        await service.create_document(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            data=DocumentCreate(uuid4(), None, None, "drawing"),
        )
    assert session.added == []


async def test_binary_intake_generates_the_object_key_and_checksum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    identity = IdentityStub()
    storage = LocalDocumentStorage(tmp_path)
    service = DocumentsService(cast(IdentityContract, identity), storage)
    row = document()
    session = SessionStub(document=row)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    content = b"%PDF-1.7 synthetic local content"
    revision = await service.add_revision_content(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        document_id=row.id,
        revision_code="A",
        content=content,
        issue_purpose="Synthetic coordination",
        issue_date=None,
    )
    assert revision.object_storage_key.startswith(f"{row.project_id}/{row.id}/")
    assert (
        storage.read(
            key=revision.object_storage_key,
            expected_sha256=revision.checksum_sha256,
        )
        == content
    )
