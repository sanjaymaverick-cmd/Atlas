"""HTTP request and response models."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atlas.modules.documents.schemas import (
    DocumentCreate,
    DocumentSummary,
    ExportRequestSummary,
    PreviewGrant,
    RevisionCreate,
    RevisionSummary,
)
from atlas.modules.organization.schemas import ProjectCreate, ProjectSummary, ProjectUpdate


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    code: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    status: str = Field(default="planning", min_length=1, max_length=100)
    start_date: date | None = None
    target_completion_date: date | None = None

    def to_dto(self, legal_entity_id: UUID) -> ProjectCreate:
        return ProjectCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, min_length=1, max_length=100)
    start_date: date | None = None
    target_completion_date: date | None = None

    def to_dto(self) -> ProjectUpdate:
        return ProjectUpdate(**self.model_dump())


class ProjectResponse(BaseModel):
    id: UUID
    legal_entity_id: UUID
    name: str
    code: str
    city: str | None
    status: str
    start_date: date | None
    target_completion_date: date | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, project: ProjectSummary) -> ProjectResponse:
        return cls(**{field: getattr(project, field) for field in cls.model_fields})


class DocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discipline: str | None = Field(default=None, max_length=100)
    drawing_number: str | None = Field(default=None, max_length=100)
    document_type: str | None = Field(default=None, max_length=100)
    classification: str = Field(
        default="internal", pattern="^(public|internal|confidential|restricted)$"
    )

    def to_dto(self, project_id: UUID) -> DocumentCreate:
        return DocumentCreate(project_id=project_id, **self.model_dump())


class DocumentResponse(BaseModel):
    id: UUID
    project_id: UUID
    discipline: str | None
    drawing_number: str | None
    document_type: str | None
    classification: str
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, document: DocumentSummary) -> DocumentResponse:
        return cls(**{field: getattr(document, field) for field in cls.model_fields})


class RevisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_code: str = Field(min_length=1, max_length=100)
    object_storage_key: str = Field(min_length=1, max_length=500)
    checksum_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    issue_purpose: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None

    @field_validator("object_storage_key")
    @classmethod
    def opaque_storage_key_only(cls, value: str) -> str:
        if value.startswith("/") or "\\" in value or "://" in value or ".." in value.split("/"):
            raise ValueError("must be an opaque object key, not a path or URL")
        return value

    def to_dto(self) -> RevisionCreate:
        return RevisionCreate(**self.model_dump())


class RevisionResponse(BaseModel):
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

    @classmethod
    def from_dto(cls, revision: RevisionSummary) -> RevisionResponse:
        return cls(**{field: getattr(revision, field) for field in cls.model_fields})


class ScanResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clean: bool


class RevisionTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(pattern="^(under_review|approved|issued)$")


class PreviewGrantResponse(BaseModel):
    id: UUID
    token: str
    expires_at: datetime
    watermark_text: str

    @classmethod
    def from_dto(cls, grant: PreviewGrant) -> PreviewGrantResponse:
        return cls(**{field: getattr(grant, field) for field in cls.model_fields})


class ExportRequestCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class ExportDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    decision_reason: str = Field(min_length=1, max_length=500)


class ExportRequestResponse(BaseModel):
    id: UUID
    document_version_id: UUID
    requested_by: UUID
    approved_by: UUID | None
    reason: str
    decision_reason: str | None
    status: str
    expires_at: datetime | None
    version: int

    @classmethod
    def from_dto(cls, request: ExportRequestSummary) -> ExportRequestResponse:
        return cls(**{field: getattr(request, field) for field in cls.model_fields})
