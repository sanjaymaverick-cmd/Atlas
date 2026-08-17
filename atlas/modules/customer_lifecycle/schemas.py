"""Published immutable Phase 8 DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BookingCreate:
    project_id: UUID
    customer_id: UUID
    unit_id: UUID
    booking_date: date
    booking_document_id: UUID | None = None
    lead_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BookingSummary:
    id: UUID
    project_id: UUID
    customer_id: UUID
    unit_id: UUID
    booking_date: date
    booking_document_id: UUID | None
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class PlanCreate:
    plan_name: str | None
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class PlanSummary:
    id: UUID
    booking_id: UUID
    plan_name: str | None
    total_amount: Decimal | None
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class InstallmentCreate:
    due_date: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class InstallmentSummary:
    id: UUID
    payment_plan_id: UUID
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class CollectionCreate:
    amount: Decimal
    received_date: date
    mode: str | None = None
    reference_number: str | None = None
    evidence_document_id: UUID | None = None
    installment_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    id: UUID
    booking_id: UUID
    installment_id: UUID | None
    amount: Decimal
    received_date: date
    status: str
    evidence_document_id: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class RegistrationTransition:
    target_status: str
    registration_date: date | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RegistrationSummary:
    id: UUID
    booking_id: UUID
    registration_date: date | None
    status: str
    evidence_document_id: UUID | None
    registered_by: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class PossessionTransition:
    target_status: str
    handover_date: date | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PossessionSummary:
    id: UUID
    booking_id: UUID
    handover_date: date | None
    status: str
    evidence_document_id: UUID | None
    handed_over_by: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class BookingContractSummary:
    id: UUID
    booking_id: UUID
    contract_id: UUID
    executed_document_id: UUID
    linked_at: datetime
    linked_by: UUID | None
    version: int
