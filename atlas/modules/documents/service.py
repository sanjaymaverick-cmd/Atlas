"""Document registry and immutable revision service."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.documents.contracts import (
    DocumentConflictError,
    DocumentNotAuthorisedError,
    DocumentNotFoundError,
)
from atlas.modules.documents.models import (
    Document,
    DocumentVersion,
    ExportRequest,
    PreviewGrantRecord,
)
from atlas.modules.documents.preview import PreviewRenderError, render_watermarked_pdf
from atlas.modules.documents.schemas import (
    DocumentCreate,
    DocumentSummary,
    ExportRequestSummary,
    PreviewGrant,
    RevisionCreate,
    RevisionSummary,
)
from atlas.modules.documents.storage import DocumentStorage, StorageError
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.access_control import DeviceTrust
from atlas.platform.audit.writer import record_event

PERM_DOCUMENT_READ = "document.read"
PERM_DOCUMENT_CREATE = "document.create"
PERM_DOCUMENT_REVISE = "document.revise"
PERM_DOCUMENT_ARCHIVE = "document.archive"
PERM_DOCUMENT_SCAN = "document.scan"
PERM_DOCUMENT_REVIEW = "document.review"
PERM_DOCUMENT_PREVIEW = "document.preview"
PERM_DOCUMENT_EXPORT_REQUEST = "document.export.request"
PERM_DOCUMENT_EXPORT_APPROVE = "document.export.approve"

PREVIEW_TTL = timedelta(minutes=10)
EXPORT_TTL = timedelta(minutes=15)

_REVISION_TRANSITIONS = {
    "virus_scanned": frozenset({"under_review"}),
    "under_review": frozenset({"approved"}),
    "approved": frozenset({"issued"}),
}


def _summary(row: Document) -> DocumentSummary:
    return DocumentSummary(
        id=row.id,
        project_id=row.project_id,
        discipline=row.discipline,
        drawing_number=row.drawing_number,
        document_type=row.document_type,
        classification=row.classification,
        status=row.status,
        version=row.version,
        archived_at=row.archived_at,
    )


def _revision_summary(row: DocumentVersion) -> RevisionSummary:
    return RevisionSummary(
        id=row.id,
        document_id=row.document_id,
        revision_code=row.revision_code,
        issue_purpose=row.issue_purpose,
        issue_date=row.issue_date,
        author_id=row.author_id,
        superseded_version_id=row.superseded_version_id,
        object_storage_key=row.object_storage_key,
        checksum_sha256=row.checksum_sha256,
        status=row.status,
        created_at=row.created_at,
    )


def _auditable(row: Document) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "discipline": row.discipline,
        "drawing_number": row.drawing_number,
        "document_type": row.document_type,
        "classification": row.classification,
        "status": row.status,
        "version": row.version,
        "archived_at": row.archived_at,
    }


def _export_summary(row: ExportRequest) -> ExportRequestSummary:
    return ExportRequestSummary(
        id=row.id,
        document_version_id=row.document_version_id,
        requested_by=row.requested_by,
        approved_by=row.approved_by,
        reason=row.reason,
        decision_reason=row.decision_reason,
        status=row.status,
        expires_at=row.expires_at,
        version=row.version,
    )


class DocumentsService:
    def __init__(self, identity: IdentityContract, storage: DocumentStorage | None = None) -> None:
        self._identity = identity
        self._storage = storage

    async def _require(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        permission: str,
        project_id: UUID,
    ) -> None:
        allowed = await self._identity.check_scoped_role(
            session,
            user_id=actor_user_id,
            permission_code=permission,
            project_id=project_id,
        )
        if not allowed:
            raise DocumentNotAuthorisedError(
                f"user {actor_user_id} may not {permission} in project {project_id}"
            )

    async def _get_authorised(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        permission: str,
    ) -> Document:
        document = await session.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError(f"document {document_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=permission,
            project_id=document.project_id,
        )
        return document

    async def _get_revision_authorised(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        permission: str,
    ) -> tuple[DocumentVersion, Document]:
        revision = await session.get(DocumentVersion, revision_id)
        if revision is None:
            raise DocumentNotFoundError(f"revision {revision_id} does not exist")
        document = await self._get_authorised(
            session,
            actor_user_id=actor_user_id,
            document_id=revision.document_id,
            permission=permission,
        )
        return revision, document

    @staticmethod
    def _require_content_device(document: Document, device_trust: DeviceTrust) -> None:
        if document.classification == "restricted" and device_trust is not DeviceTrust.ELEVATED:
            raise DocumentNotAuthorisedError(
                "restricted document content requires an elevated-trust device"
            )

    async def get_document(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary:
        return _summary(
            await self._get_authorised(
                session,
                actor_user_id=actor_user_id,
                document_id=document_id,
                permission=PERM_DOCUMENT_READ,
            )
        )

    async def list_documents(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[DocumentSummary]:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_DOCUMENT_READ,
            project_id=project_id,
        )
        result = await session.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .where(Document.archived_at.is_(None))
            .order_by(Document.drawing_number, Document.created_at)
        )
        return [_summary(row) for row in result.scalars()]

    async def create_document(
        self, session: AsyncSession, *, actor_user_id: UUID, data: DocumentCreate
    ) -> DocumentSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_DOCUMENT_CREATE,
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        document = Document(
            id=uuid4(),
            project_id=data.project_id,
            building_id=None,
            floor_id=None,
            unit_id=None,
            discipline=data.discipline,
            drawing_number=data.drawing_number,
            document_type=data.document_type,
            classification=data.classification,
            status="uploaded",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(document)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise DocumentConflictError("document metadata conflicts with existing data") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="documents",
            entity_id=document.id,
            action="create",
            after_state=_auditable(document),
        )
        return _summary(document)

    async def record_scan_result(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        clean: bool,
    ) -> RevisionSummary:
        revision, _ = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=revision_id,
            permission=PERM_DOCUMENT_SCAN,
        )
        if revision.status != "draft":
            raise DocumentConflictError("only a draft revision may receive a scan result")
        before = {"status": revision.status}
        revision.status = "virus_scanned" if clean else "quarantined"
        revision.updated_at = datetime.now(UTC)
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="document_versions",
            entity_id=revision.id,
            action="malware_scan_clean" if clean else "malware_scan_quarantine",
            before_state=before,
            after_state={"status": revision.status},
        )
        return _revision_summary(revision)

    async def transition_revision(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        target_status: str,
    ) -> RevisionSummary:
        revision, _ = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=revision_id,
            permission=PERM_DOCUMENT_REVIEW,
        )
        if target_status not in _REVISION_TRANSITIONS.get(revision.status, frozenset()):
            raise DocumentConflictError(
                f"revision cannot move from {revision.status} to {target_status}"
            )
        before = {"status": revision.status}
        revision.status = target_status
        revision.updated_at = datetime.now(UTC)
        if target_status == "approved":
            revision.approver_id = actor_user_id
        elif target_status == "under_review":
            revision.reviewer_id = actor_user_id
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="document_versions",
            entity_id=revision.id,
            action=f"transition_{target_status}",
            before_state=before,
            after_state={"status": revision.status},
        )
        return _revision_summary(revision)

    async def create_preview_grant(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        revision_id: UUID,
        device_trust: DeviceTrust,
    ) -> PreviewGrant:
        revision, document = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=revision_id,
            permission=PERM_DOCUMENT_PREVIEW,
        )
        if revision.status not in {"virus_scanned", "under_review", "approved", "issued"}:
            raise DocumentConflictError("revision is not cleared for preview")
        self._require_content_device(document, device_trust)
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        watermark = f"ATLAS user:{actor_user_id} session:{session_id} utc:{now.isoformat()}"
        row = PreviewGrantRecord(
            id=uuid4(),
            document_version_id=revision.id,
            session_id=session_id,
            created_by=actor_user_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            watermark_text=watermark,
            expires_at=now + PREVIEW_TTL,
            revoked_at=None,
            created_at=now,
        )
        session.add(row)
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="preview_grants",
            entity_id=row.id,
            action="create",
            after_state={
                "document_version_id": str(revision.id),
                "session_id": str(session_id),
                "expires_at": row.expires_at,
            },
        )
        return PreviewGrant(row.id, token, row.expires_at, watermark)

    async def render_preview(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        token: str,
        device_trust: DeviceTrust,
    ) -> bytes:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = await session.scalar(
            select(PreviewGrantRecord).where(PreviewGrantRecord.token_hash == token_hash)
        )
        now = datetime.now(UTC)
        if (
            row is None
            or row.session_id != session_id
            or row.created_by != actor_user_id
            or row.revoked_at is not None
            or row.expires_at <= now
        ):
            raise DocumentNotAuthorisedError("preview grant is invalid or expired")
        revision, document = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=row.document_version_id,
            permission=PERM_DOCUMENT_PREVIEW,
        )
        self._require_content_device(document, device_trust)
        if self._storage is None:
            raise DocumentConflictError("document storage is not configured")
        try:
            content = self._storage.read(
                key=revision.object_storage_key,
                expected_sha256=revision.checksum_sha256,
            )
            rendered = render_watermarked_pdf(content, watermark_text=row.watermark_text)
        except (StorageError, PreviewRenderError) as exc:
            raise DocumentConflictError("document preview is unavailable") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="preview_grants",
            entity_id=row.id,
            action="view",
            after_state={
                "document_version_id": str(revision.id),
                "session_id": str(session_id),
            },
        )
        return rendered

    async def request_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary:
        revision, document = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=revision_id,
            permission=PERM_DOCUMENT_EXPORT_REQUEST,
        )
        self._require_content_device(document, device_trust)
        if revision.status not in {"approved", "issued"}:
            raise DocumentConflictError("only approved or issued revisions may be exported")
        now = datetime.now(UTC)
        row = ExportRequest(
            id=uuid4(),
            document_version_id=revision.id,
            requested_by=actor_user_id,
            approved_by=None,
            reason=reason,
            decision_reason=None,
            status="pending",
            expires_at=None,
            created_at=now,
            updated_at=now,
            version=1,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise DocumentConflictError("a pending export request already exists") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="export_requests",
            entity_id=row.id,
            action="request",
            after_state={"status": row.status, "document_version_id": str(revision.id)},
        )
        return _export_summary(row)

    async def decide_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        approve: bool,
        decision_reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary:
        row = await session.get(ExportRequest, request_id)
        if row is None:
            raise DocumentNotFoundError(f"export request {request_id} does not exist")
        revision, document = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=row.document_version_id,
            permission=PERM_DOCUMENT_EXPORT_APPROVE,
        )
        self._require_content_device(document, device_trust)
        if row.status != "pending":
            raise DocumentConflictError("export request has already been decided")
        if row.requested_by == actor_user_id:
            raise DocumentNotAuthorisedError("requesters may not approve their own exports")
        if revision.status not in {"approved", "issued"}:
            raise DocumentConflictError("revision is no longer eligible for export")
        before = {"status": row.status, "version": row.version}
        now = datetime.now(UTC)
        row.status = "approved" if approve else "rejected"
        row.approved_by = actor_user_id
        row.decision_reason = decision_reason
        row.expires_at = now + EXPORT_TTL if approve else None
        row.updated_at = now
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="export_requests",
            entity_id=row.id,
            action=row.status,
            before_state=before,
            after_state={
                "status": row.status,
                "version": row.version,
                "expires_at": row.expires_at,
            },
        )
        return _export_summary(row)

    async def download_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        device_trust: DeviceTrust,
    ) -> bytes:
        row = await session.get(ExportRequest, request_id)
        now = datetime.now(UTC)
        if row is None:
            raise DocumentNotFoundError(f"export request {request_id} does not exist")
        if row.requested_by != actor_user_id:
            raise DocumentNotAuthorisedError("only the requester may download this export")
        if row.status != "approved" or row.expires_at is None or row.expires_at <= now:
            raise DocumentConflictError("export approval is unavailable or expired")
        revision, document = await self._get_revision_authorised(
            session,
            actor_user_id=actor_user_id,
            revision_id=row.document_version_id,
            permission=PERM_DOCUMENT_EXPORT_REQUEST,
        )
        self._require_content_device(document, device_trust)
        if self._storage is None:
            raise DocumentConflictError("document storage is not configured")
        try:
            content = self._storage.read(
                key=revision.object_storage_key,
                expected_sha256=revision.checksum_sha256,
            )
        except StorageError as exc:
            raise DocumentConflictError("approved export failed its integrity check") from exc
        before = {"status": row.status, "version": row.version}
        row.status = "downloaded"
        row.updated_at = now
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="export_requests",
            entity_id=row.id,
            action="download",
            before_state=before,
            after_state={"status": row.status, "version": row.version},
        )
        return content

    async def add_revision(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        data: RevisionCreate,
    ) -> RevisionSummary:
        document = await self._get_authorised(
            session,
            actor_user_id=actor_user_id,
            document_id=document_id,
            permission=PERM_DOCUMENT_REVISE,
        )
        if document.archived_at is not None:
            raise DocumentConflictError("an archived document cannot receive a revision")
        if self._storage is not None:
            try:
                self._storage.read(
                    key=data.object_storage_key,
                    expected_sha256=data.checksum_sha256,
                )
            except StorageError as exc:
                raise DocumentConflictError(
                    "revision object is missing or failed integrity"
                ) from exc
        latest = await session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.created_at.desc())
            .limit(1)
        )
        now = datetime.now(UTC)
        revision = DocumentVersion(
            id=uuid4(),
            document_id=document.id,
            revision_code=data.revision_code,
            issue_purpose=data.issue_purpose,
            issue_date=data.issue_date,
            author_id=actor_user_id,
            reviewer_id=None,
            approver_id=None,
            superseded_version_id=latest.id if latest is not None else None,
            related_change_request_id=None,
            object_storage_key=data.object_storage_key,
            checksum_sha256=data.checksum_sha256,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        before = _auditable(document)
        document.version += 1
        document.updated_at = now
        document.updated_by = actor_user_id
        session.add(revision)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise DocumentConflictError("revision code or storage object already exists") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="document_versions",
            entity_id=revision.id,
            action="create_revision",
            before_state=before,
            after_state={
                **_auditable(document),
                "revision_code": revision.revision_code,
                "checksum_sha256": revision.checksum_sha256,
                "superseded_version_id": revision.superseded_version_id,
            },
        )
        return _revision_summary(revision)

    async def add_revision_content(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        revision_code: str,
        content: bytes,
        issue_purpose: str | None,
        issue_date: date | None,
    ) -> RevisionSummary:
        document = await self._get_authorised(
            session,
            actor_user_id=actor_user_id,
            document_id=document_id,
            permission=PERM_DOCUMENT_REVISE,
        )
        if self._storage is None:
            raise DocumentConflictError("document storage is not configured")
        checksum = hashlib.sha256(content).hexdigest()
        key = f"{document.project_id}/{document.id}/{uuid4()}"
        try:
            self._storage.put(key=key, content=content, expected_sha256=checksum)
        except StorageError as exc:
            raise DocumentConflictError("document content could not be stored") from exc
        return await self.add_revision(
            session,
            actor_user_id=actor_user_id,
            document_id=document.id,
            data=RevisionCreate(
                revision_code=revision_code,
                object_storage_key=key,
                checksum_sha256=checksum,
                issue_purpose=issue_purpose,
                issue_date=issue_date,
            ),
        )

    async def list_revisions(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> list[RevisionSummary]:
        document = await self._get_authorised(
            session,
            actor_user_id=actor_user_id,
            document_id=document_id,
            permission=PERM_DOCUMENT_READ,
        )
        result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.created_at)
        )
        return [_revision_summary(row) for row in result.scalars()]

    async def archive_document(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary:
        document = await self._get_authorised(
            session,
            actor_user_id=actor_user_id,
            document_id=document_id,
            permission=PERM_DOCUMENT_ARCHIVE,
        )
        if document.archived_at is not None:
            return _summary(document)
        before = _auditable(document)
        now = datetime.now(UTC)
        document.archived_at = now
        document.status = "archived"
        document.updated_at = now
        document.updated_by = actor_user_id
        document.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="documents",
            entity_table="documents",
            entity_id=document.id,
            action="archive",
            before_state=before,
            after_state=_auditable(document),
        )
        return _summary(document)
