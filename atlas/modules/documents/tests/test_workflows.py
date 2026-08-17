"""Preview, review, malware-scan, and export-approval workflow tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import fitz
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.documents import service as service_module
from atlas.modules.documents.contracts import (
    DocumentConflictError,
    DocumentNotAuthorisedError,
)
from atlas.modules.documents.models import (
    Document,
    DocumentVersion,
    ExportRequest,
    PreviewGrantRecord,
)
from atlas.modules.documents.service import DocumentsService
from atlas.modules.documents.storage import LocalDocumentStorage
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.access_control import DeviceTrust

pytestmark = pytest.mark.unit


class IdentityStub:
    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return True


class WorkflowSession:
    def __init__(
        self,
        *,
        document: Document,
        revision: DocumentVersion,
        export: ExportRequest | None = None,
        preview: PreviewGrantRecord | None = None,
    ) -> None:
        self.document = document
        self.revision = revision
        self.export = export
        self.preview = preview
        self.added: list[object] = []

    async def get(self, model: object, key: UUID) -> object | None:
        if model is Document:
            return self.document
        if model is DocumentVersion:
            return self.revision
        if model is ExportRequest:
            return self.export
        return None

    async def scalar(self, statement: object) -> object | None:
        return self.preview

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, ExportRequest):
            self.export = value

    async def flush(self) -> None:
        return None


async def ignore_audit(*args: object, **kwargs: object) -> None:
    return None


def records(*, status: str = "draft") -> tuple[Document, DocumentVersion]:
    now = datetime.now(UTC)
    document = Document(
        id=uuid4(),
        project_id=uuid4(),
        building_id=None,
        floor_id=None,
        unit_id=None,
        discipline="architectural",
        drawing_number="SYN-A-001",
        document_type="drawing",
        classification="confidential",
        status="uploaded",
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=1,
        archived_at=None,
    )
    revision = DocumentVersion(
        id=uuid4(),
        document_id=document.id,
        revision_code="A",
        issue_purpose=None,
        issue_date=None,
        author_id=uuid4(),
        reviewer_id=None,
        approver_id=None,
        superseded_version_id=None,
        related_change_request_id=None,
        object_storage_key="synthetic/object",
        checksum_sha256="a" * 64,
        status=status,
        created_at=now,
        updated_at=now,
    )
    return document, revision


def service() -> DocumentsService:
    return DocumentsService(cast(IdentityContract, IdentityStub()))


def pdf_bytes() -> bytes:
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Synthetic controlled drawing")
    content = document.tobytes()
    document.close()
    return content


async def test_scan_result_quarantines_or_clears_only_a_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, revision = records()
    session = WorkflowSession(document=document, revision=revision)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    result = await service().record_scan_result(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        revision_id=revision.id,
        clean=False,
    )
    assert result.status == "quarantined"
    with pytest.raises(DocumentConflictError):
        await service().record_scan_result(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            revision_id=revision.id,
            clean=True,
        )


async def test_revision_review_transitions_are_linear(monkeypatch: pytest.MonkeyPatch) -> None:
    document, revision = records(status="virus_scanned")
    session = WorkflowSession(document=document, revision=revision)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    reviewer = uuid4()
    reviewed = await service().transition_revision(
        cast(AsyncSession, session),
        actor_user_id=reviewer,
        revision_id=revision.id,
        target_status="under_review",
    )
    assert reviewed.status == "under_review"
    assert revision.reviewer_id == reviewer
    with pytest.raises(DocumentConflictError):
        await service().transition_revision(
            cast(AsyncSession, session),
            actor_user_id=reviewer,
            revision_id=revision.id,
            target_status="issued",
        )


async def test_preview_token_is_hashed_and_watermark_is_session_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, revision = records(status="approved")
    session = WorkflowSession(document=document, revision=revision)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    actor_id = uuid4()
    session_id = uuid4()
    grant = await service().create_preview_grant(
        cast(AsyncSession, session),
        actor_user_id=actor_id,
        session_id=session_id,
        revision_id=revision.id,
        device_trust=DeviceTrust.ELEVATED,
    )
    stored = cast(PreviewGrantRecord, session.added[0])
    assert stored.token_hash == hashlib.sha256(grant.token.encode()).hexdigest()
    assert grant.token not in stored.watermark_text
    assert str(actor_id) in grant.watermark_text
    assert str(session_id) in grant.watermark_text


async def test_restricted_preview_requires_elevated_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, revision = records(status="approved")
    document.classification = "restricted"
    session = WorkflowSession(document=document, revision=revision)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    with pytest.raises(DocumentNotAuthorisedError, match="elevated-trust"):
        await service().create_preview_grant(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            session_id=uuid4(),
            revision_id=revision.id,
            device_trust=DeviceTrust.STANDARD,
        )
    assert session.added == []


async def test_export_enforces_four_eyes_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    document, revision = records(status="approved")
    session = WorkflowSession(document=document, revision=revision)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    requester = uuid4()
    requested = await service().request_export(
        cast(AsyncSession, session),
        actor_user_id=requester,
        revision_id=revision.id,
        reason="Synthetic controlled export",
        device_trust=DeviceTrust.ELEVATED,
    )
    assert requested.status == "pending"
    with pytest.raises(DocumentNotAuthorisedError):
        await service().decide_export(
            cast(AsyncSession, session),
            actor_user_id=requester,
            request_id=requested.id,
            approve=True,
            decision_reason="Self approval must fail",
            device_trust=DeviceTrust.ELEVATED,
        )

    approver = uuid4()
    approved = await service().decide_export(
        cast(AsyncSession, session),
        actor_user_id=approver,
        request_id=requested.id,
        approve=True,
        decision_reason="Synthetic approval",
        device_trust=DeviceTrust.ELEVATED,
    )
    assert approved.status == "approved"
    assert approved.approved_by == approver
    assert approved.expires_at is not None
    assert approved.version == 2


async def test_preview_render_requires_the_originating_session_and_verifies_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document, revision = records(status="approved")
    actor_id = uuid4()
    session_id = uuid4()
    token = "synthetic-preview-token"  # noqa: S105
    watermark = f"ATLAS user:{actor_id} session:{session_id}"
    preview = PreviewGrantRecord(
        id=uuid4(),
        document_version_id=revision.id,
        session_id=session_id,
        created_by=actor_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        watermark_text=watermark,
        expires_at=datetime.now(UTC) + service_module.PREVIEW_TTL,
        revoked_at=None,
        created_at=datetime.now(UTC),
    )
    session = WorkflowSession(document=document, revision=revision, preview=preview)
    storage = LocalDocumentStorage(tmp_path)
    content = pdf_bytes()
    revision.object_storage_key = "synthetic/object.pdf"
    revision.checksum_sha256 = hashlib.sha256(content).hexdigest()
    storage.put(
        key=revision.object_storage_key,
        content=content,
        expected_sha256=revision.checksum_sha256,
    )
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    documents = DocumentsService(cast(IdentityContract, IdentityStub()), storage)
    rendered = await documents.render_preview(
        cast(AsyncSession, session),
        actor_user_id=actor_id,
        session_id=session_id,
        token=token,
        device_trust=DeviceTrust.ELEVATED,
    )
    rendered_pdf = fitz.open(stream=rendered, filetype="pdf")
    try:
        rendered_text = rendered_pdf[0].get_text()
        assert f"ATLAS user:{actor_id}" in rendered_text
        assert f"session:{session_id}" in rendered_text
    finally:
        rendered_pdf.close()

    with pytest.raises(DocumentNotAuthorisedError):
        await documents.render_preview(
            cast(AsyncSession, session),
            actor_user_id=actor_id,
            session_id=uuid4(),
            token=token,
            device_trust=DeviceTrust.ELEVATED,
        )


async def test_approved_export_is_integrity_checked_and_single_use(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document, revision = records(status="approved")
    requester = uuid4()
    now = datetime.now(UTC)
    export = ExportRequest(
        id=uuid4(),
        document_version_id=revision.id,
        requested_by=requester,
        approved_by=uuid4(),
        reason="Synthetic export",
        decision_reason="Synthetic approval",
        status="approved",
        expires_at=now + service_module.EXPORT_TTL,
        created_at=now,
        updated_at=now,
        version=2,
    )
    session = WorkflowSession(document=document, revision=revision, export=export)
    storage = LocalDocumentStorage(tmp_path)
    content = b"synthetic approved export"
    revision.object_storage_key = "synthetic/export"
    revision.checksum_sha256 = hashlib.sha256(content).hexdigest()
    storage.put(
        key=revision.object_storage_key,
        content=content,
        expected_sha256=revision.checksum_sha256,
    )
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    documents = DocumentsService(cast(IdentityContract, IdentityStub()), storage)
    downloaded = await documents.download_export(
        cast(AsyncSession, session),
        actor_user_id=requester,
        request_id=export.id,
        device_trust=DeviceTrust.ELEVATED,
    )
    assert downloaded == content
    assert export.status == "downloaded"
    assert export.version == 3
    with pytest.raises(DocumentConflictError):
        await documents.download_export(
            cast(AsyncSession, session),
            actor_user_id=requester,
            request_id=export.id,
            device_trust=DeviceTrust.ELEVATED,
        )
