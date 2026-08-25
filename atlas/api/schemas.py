"""HTTP request and response models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atlas.modules.compliance.schemas import (
    ComplianceObligationCreate,
    ComplianceObligationSummary,
    ReraRegistrationCreate,
    ReraRegistrationSummary,
)
from atlas.modules.documents.schemas import (
    DocumentCreate,
    DocumentSummary,
    ExportRequestSummary,
    PreviewGrant,
    RevisionCreate,
    RevisionSummary,
)
from atlas.modules.land.schemas import (
    DueDiligenceCreate,
    DueDiligenceSummary,
    InstallmentCreate,
    InstallmentSummary,
    LandParcelCreate,
    LandParcelSummary,
    LegalApprovalCreate,
    LegalApprovalSummary,
    LoanCreate,
    LoanSummary,
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


class LifecycleTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=50)


class LandParcelCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID | None = None
    survey_number: str | None = Field(default=None, max_length=200)
    area_sqft: Decimal | None = Field(default=None, gt=0)
    location: str | None = Field(default=None, max_length=500)

    def to_dto(self, legal_entity_id: UUID) -> LandParcelCreate:
        return LandParcelCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class LandParcelResponse(BaseModel):
    id: UUID
    legal_entity_id: UUID
    project_id: UUID | None
    survey_number: str | None
    area_sqft: Decimal | None
    location: str | None
    acquisition_status: str
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: LandParcelSummary) -> LandParcelResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class DueDiligenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    evidence_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    def to_dto(self) -> DueDiligenceCreate:
        return DueDiligenceCreate(**self.model_dump())


class DueDiligenceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str = Field(pattern="^(clear|issue|waived)$")
    notes: str | None = Field(default=None, max_length=2000)


class DueDiligenceResponse(BaseModel):
    id: UUID
    land_parcel_id: UUID
    category: str
    title: str
    result: str
    evidence_document_id: UUID | None
    notes: str | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: DueDiligenceSummary) -> DueDiligenceResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class LegalApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_type: str = Field(min_length=1, max_length=100)
    authority: str | None = Field(default=None, max_length=200)
    reference_number: str | None = Field(default=None, max_length=200)
    valid_from: date | None = None
    valid_to: date | None = None

    def to_dto(self) -> LegalApprovalCreate:
        return LegalApprovalCreate(**self.model_dump())


class LegalApprovalResponse(BaseModel):
    id: UUID
    land_parcel_id: UUID | None
    project_id: UUID | None
    approval_type: str
    authority: str | None
    reference_number: str | None
    valid_from: date | None
    valid_to: date | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: LegalApprovalSummary) -> LegalApprovalResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class LoanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID | None = None
    lender_name: str = Field(min_length=1, max_length=300)
    principal_amount: Decimal | None = Field(default=None, ge=0)
    emi_amount: Decimal | None = Field(default=None, ge=0)
    emi_due_day: int | None = Field(default=None, ge=1, le=31)

    def to_dto(self, legal_entity_id: UUID) -> LoanCreate:
        return LoanCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class LoanResponse(BaseModel):
    id: UUID
    legal_entity_id: UUID
    project_id: UUID | None
    lender_name: str
    principal_amount: Decimal | None
    emi_amount: Decimal | None
    emi_due_day: int | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: LoanSummary) -> LoanResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class InstallmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_date: date
    amount: Decimal = Field(ge=0)
    instrument_type: str = Field(default="emi", pattern="^(emi|pdc|other)$")
    reference_number: str | None = Field(default=None, max_length=200)

    def to_dto(self) -> InstallmentCreate:
        return InstallmentCreate(**self.model_dump())


class InstallmentResponse(BaseModel):
    id: UUID
    loan_obligation_id: UUID
    due_date: date
    amount: Decimal
    instrument_type: str
    reference_number: str | None
    status: str
    paid_at: datetime | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: InstallmentSummary) -> InstallmentResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class ReraRegistrationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    registration_number: str = Field(min_length=1, max_length=200)
    valid_from: date | None = None
    valid_to: date | None = None

    def to_dto(self, project_id: UUID) -> ReraRegistrationCreate:
        return ReraRegistrationCreate(project_id=project_id, **self.model_dump())


class ReraRegistrationResponse(BaseModel):
    id: UUID
    project_id: UUID
    registration_number: str
    valid_from: date | None
    valid_to: date | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: ReraRegistrationSummary) -> ReraRegistrationResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})


class ComplianceObligationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_entity_id: UUID | None = None
    project_id: UUID | None = None
    obligation_type: str = Field(min_length=1, max_length=100)
    authority: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)

    def to_dto(self) -> ComplianceObligationCreate:
        return ComplianceObligationCreate(**self.model_dump())


class ComplianceObligationResponse(BaseModel):
    id: UUID
    legal_entity_id: UUID | None
    project_id: UUID | None
    obligation_type: str
    authority: str | None
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: ComplianceObligationSummary) -> ComplianceObligationResponse:
        return cls(**{field: getattr(value, field) for field in cls.model_fields})
