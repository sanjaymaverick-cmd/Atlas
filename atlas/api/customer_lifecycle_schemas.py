"""Validated HTTP models for Phase 8 customer lifecycle."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.customer_lifecycle.schemas import (
    BookingCreate,
    CollectionCreate,
    InstallmentCreate,
    PlanCreate,
    PossessionTransition,
    RegistrationTransition,
)


class DtoResponse(BaseModel):
    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(**{f: getattr(value, f) for f in cls.model_fields})


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    unit_id: UUID
    booking_date: date
    booking_document_id: UUID | None = None
    lead_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> BookingCreate:
        return BookingCreate(project_id=project_id, **self.model_dump())


class BookingResponse(DtoResponse):
    id: UUID
    project_id: UUID
    customer_id: UUID
    unit_id: UUID
    booking_date: date
    booking_document_id: UUID | None
    status: str
    version: int


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_name: str | None = Field(default=None, max_length=200)
    total_amount: Decimal = Field(ge=0)

    def to_dto(self) -> PlanCreate:
        return PlanCreate(**self.model_dump())


class PlanResponse(DtoResponse):
    id: UUID
    booking_id: UUID
    plan_name: str | None
    total_amount: Decimal | None
    status: str
    version: int


class InstallmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_date: date
    amount: Decimal = Field(gt=0)

    def to_dto(self) -> InstallmentCreate:
        return InstallmentCreate(**self.model_dump())


class InstallmentResponse(DtoResponse):
    id: UUID
    payment_plan_id: UUID
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(gt=0)
    received_date: date
    mode: str | None = Field(default=None, max_length=50)
    reference_number: str | None = Field(default=None, max_length=200)
    evidence_document_id: UUID | None = None
    installment_id: UUID | None = None

    def to_dto(self) -> CollectionCreate:
        return CollectionCreate(**self.model_dump())


class CollectionResponse(DtoResponse):
    id: UUID
    booking_id: UUID
    installment_id: UUID | None
    amount: Decimal
    received_date: date
    status: str
    evidence_document_id: UUID | None
    version: int


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(pattern="^(scheduled|registered|cancelled)$")
    registration_date: date | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self) -> RegistrationTransition:
        return RegistrationTransition(**self.model_dump())


class RegistrationResponse(DtoResponse):
    id: UUID
    booking_id: UUID
    registration_date: date | None
    status: str
    evidence_document_id: UUID | None
    registered_by: UUID | None
    version: int


class PossessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(pattern="^(snag_review|handed_over)$")
    handover_date: date | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self) -> PossessionTransition:
        return PossessionTransition(**self.model_dump())


class PossessionResponse(DtoResponse):
    id: UUID
    booking_id: UUID
    handover_date: date | None
    status: str
    evidence_document_id: UUID | None
    handed_over_by: UUID | None
    version: int


class ContractLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: UUID


class BookingContractResponse(DtoResponse):
    id: UUID
    booking_id: UUID
    contract_id: UUID
    executed_document_id: UUID
    linked_at: datetime
    linked_by: UUID | None
    version: int
