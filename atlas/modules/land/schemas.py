"""Published DTOs for Phase 3 land and financing workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LandParcelCreate:
    legal_entity_id: UUID
    project_id: UUID | None
    survey_number: str | None
    area_sqft: Decimal | None
    location: str | None


@dataclass(frozen=True, slots=True)
class LandParcelSummary:
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


@dataclass(frozen=True, slots=True)
class DueDiligenceCreate:
    category: str
    title: str
    evidence_document_id: UUID | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DueDiligenceSummary:
    id: UUID
    land_parcel_id: UUID
    category: str
    title: str
    result: str
    evidence_document_id: UUID | None
    notes: str | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class LegalApprovalCreate:
    approval_type: str
    authority: str | None = None
    reference_number: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(frozen=True, slots=True)
class LegalApprovalSummary:
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


@dataclass(frozen=True, slots=True)
class LoanCreate:
    legal_entity_id: UUID
    project_id: UUID | None
    lender_name: str
    principal_amount: Decimal | None
    emi_amount: Decimal | None
    emi_due_day: int | None


@dataclass(frozen=True, slots=True)
class LoanSummary:
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


@dataclass(frozen=True, slots=True)
class InstallmentCreate:
    due_date: date
    amount: Decimal
    instrument_type: str = "emi"
    reference_number: str | None = None


@dataclass(frozen=True, slots=True)
class InstallmentSummary:
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
