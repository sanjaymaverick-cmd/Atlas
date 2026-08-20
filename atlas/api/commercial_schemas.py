"""Validated HTTP models for Phase 4 commercial APIs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atlas.modules.commercial.schemas import (
    BudgetCreate,
    BudgetLineCreate,
    ContractCreate,
    ContractExecution,
    InsuranceCreate,
    KycRecordCreate,
    LabourComplianceCreate,
    MilestoneCreate,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
)


def dto_fields(model: type[BaseModel], value: Any) -> dict[str, Any]:
    return {field: getattr(value, field) for field in model.model_fields}


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=50)


class BudgetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_entity_id: UUID
    total_amount: Decimal = Field(ge=0)

    def to_dto(self, project_id: UUID) -> BudgetCreate:
        return BudgetCreate(project_id, self.legal_entity_id, self.total_amount)


class BudgetResponse(BaseModel):
    id: UUID
    project_id: UUID
    legal_entity_id: UUID
    total_amount: Decimal
    status: str
    approved_at: datetime | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> BudgetResponse:
        return cls(**dto_fields(cls, value))


class BudgetLineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cost_code_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    planned_amount: Decimal = Field(ge=0)

    def to_dto(self) -> BudgetLineCreate:
        return BudgetLineCreate(**self.model_dump())


class BudgetLineResponse(BaseModel):
    id: UUID
    budget_id: UUID
    cost_code_id: UUID | None
    description: str | None
    planned_amount: Decimal
    committed_amount: Decimal
    actual_amount: Decimal
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> BudgetLineResponse:
        return cls(**dto_fields(cls, value))


class OnboardingResponse(BaseModel):
    id: UUID
    vendor_id: UUID
    status: str
    approved_by: UUID | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> OnboardingResponse:
        return cls(**dto_fields(cls, value))


class KycCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID
    document_type: str = Field(min_length=1, max_length=100)
    document_reference: str | None = Field(default=None, max_length=200)
    evidence_document_id: UUID

    def to_dto(self) -> KycRecordCreate:
        return KycRecordCreate(**self.model_dump())


class KycDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


class KycResponse(BaseModel):
    id: UUID
    party_id: UUID
    document_type: str
    document_reference: str | None
    evidence_document_id: UUID | None
    verification_status: str
    verified_by: UUID | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> KycResponse:
        return cls(**dto_fields(cls, value))


class PurchaseOrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_id: UUID
    budget_line_id: UUID | None = None
    total_amount: Decimal = Field(ge=0)

    def to_dto(self, project_id: UUID) -> PurchaseOrderCreate:
        return PurchaseOrderCreate(project_id=project_id, **self.model_dump())


class PurchaseOrderResponse(BaseModel):
    id: UUID
    project_id: UUID
    vendor_id: UUID
    budget_line_id: UUID | None
    total_amount: Decimal
    status: str
    issued_at: datetime | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> PurchaseOrderResponse:
        return cls(**dto_fields(cls, value))


class PurchaseOrderLineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cost_code_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    amount: Decimal | None = Field(default=None, ge=0)

    def to_dto(self) -> PurchaseOrderLineCreate:
        return PurchaseOrderLineCreate(**self.model_dump())


class PurchaseOrderLineResponse(BaseModel):
    id: UUID
    purchase_order_id: UUID
    cost_code_id: UUID | None
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> PurchaseOrderLineResponse:
        return cls(**dto_fields(cls, value))


class ContractCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID
    contract_type: str | None = Field(default=None, max_length=100)
    value: Decimal | None = Field(default=None, ge=0)

    def to_dto(self, project_id: UUID) -> ContractCreate:
        return ContractCreate(project_id=project_id, **self.model_dump())


class ContractTransitionRequest(TransitionRequest):
    execution_method: str | None = Field(default=None, max_length=100)
    executed_document_id: UUID | None = None

    @model_validator(mode="after")
    def complete_execution_evidence(self) -> ContractTransitionRequest:
        if (self.execution_method is None) != (self.executed_document_id is None):
            raise ValueError("execution method and document must be supplied together")
        return self

    def execution(self) -> ContractExecution | None:
        if self.execution_method is None and self.executed_document_id is None:
            return None
        return ContractExecution(
            cast(str, self.execution_method), cast(UUID, self.executed_document_id)
        )


class ContractResponse(BaseModel):
    id: UUID
    project_id: UUID
    party_id: UUID
    contract_type: str | None
    value: Decimal | None
    status: str
    execution_method: str | None
    executed_at: datetime | None
    executed_document_id: UUID | None
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> ContractResponse:
        return cls(**dto_fields(cls, value))


class MilestoneCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = Field(default=None, max_length=500)
    due_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)

    def to_dto(self) -> MilestoneCreate:
        return MilestoneCreate(**self.model_dump())


class MilestoneResponse(BaseModel):
    id: UUID
    contract_id: UUID
    description: str | None
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> MilestoneResponse:
        return cls(**dto_fields(cls, value))


class InsuranceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID | None = None
    contract_id: UUID | None = None
    vendor_id: UUID | None = None
    policy_number: str = Field(min_length=1, max_length=200)
    insurer: str | None = Field(default=None, max_length=200)
    coverage_type: str = Field(pattern="^(CAR|professional_indemnity|other)$")
    sum_insured: Decimal | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_to: date | None = None

    def to_dto(self) -> InsuranceCreate:
        return InsuranceCreate(**self.model_dump())


class InsuranceResponse(BaseModel):
    id: UUID
    project_id: UUID | None
    contract_id: UUID | None
    vendor_id: UUID | None
    policy_number: str
    insurer: str | None
    coverage_type: str
    sum_insured: Decimal | None
    valid_from: date | None
    valid_to: date | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> InsuranceResponse:
        return cls(**dto_fields(cls, value))


class LabourCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contractor_id: UUID
    project_id: UUID | None = None
    pf_registration_number: str | None = Field(default=None, max_length=100)
    esi_registration_number: str | None = Field(default=None, max_length=100)
    contract_labour_licence_number: str | None = Field(default=None, max_length=100)
    minimum_wage_evidence_ref: str | None = Field(default=None, max_length=200)

    def to_dto(self) -> LabourComplianceCreate:
        return LabourComplianceCreate(**self.model_dump())


class LabourResponse(BaseModel):
    id: UUID
    contractor_id: UUID
    project_id: UUID | None
    pf_registration_number: str | None
    esi_registration_number: str | None
    contract_labour_licence_number: str | None
    minimum_wage_evidence_ref: str | None
    status: str
    version: int
    archived_at: datetime | None

    @classmethod
    def from_dto(cls, value: Any) -> LabourResponse:
        return cls(**dto_fields(cls, value))
