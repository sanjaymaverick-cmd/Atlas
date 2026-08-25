"""Documents DTOs — the module's published surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DocumentCreate:
    project_id: UUID
    discipline: str | None
    drawing_number: str | None
    document_type: str | None
    classification: str = "internal"


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    id: UUID
    project_id: UUID
    discipline: str | None
    drawing_number: str | None
    document_type: str | None
    classification: str
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class RevisionCreate:
    revision_code: str
    object_storage_key: str
    checksum_sha256: str
    issue_purpose: str | None = None
    issue_date: date | None = None


@dataclass(frozen=True, slots=True)
class RevisionSummary:
    id: UUID
    document_id: UUID
    revision_code: str
    issue_purpose: str | None
    issue_date: date | None
    author_id: UUID | None
    superseded_version_id: UUID | None
    object_storage_key: str
    checksum_sha256: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PreviewGrant:
    id: UUID
    token: str
    expires_at: datetime
    watermark_text: str


@dataclass(frozen=True, slots=True)
class ExportRequestSummary:
    id: UUID
    document_version_id: UUID
    requested_by: UUID
    approved_by: UUID | None
    reason: str
    decision_reason: str | None
    status: str
    expires_at: datetime | None
    version: int
