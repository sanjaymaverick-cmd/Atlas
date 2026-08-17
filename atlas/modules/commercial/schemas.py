"""Published Phase 4 commercial DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BudgetCreate:
    project_id: UUID
    legal_entity_id: UUID
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class BudgetSummary:
    id: UUID
    project_id: UUID
    legal_entity_id: UUID
    total_amount: Decimal
    status: str
    approved_at: datetime | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class BudgetLineCreate:
    cost_code_id: UUID | None
    description: str | None
    planned_amount: Decimal


@dataclass(frozen=True, slots=True)
class BudgetLineSummary:
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


@dataclass(frozen=True, slots=True)
class VendorOnboardingSummary:
    id: UUID
    vendor_id: UUID
    status: str
    approved_by: UUID | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class KycRecordCreate:
    party_id: UUID
    document_type: str
    document_reference: str | None
    evidence_document_id: UUID


@dataclass(frozen=True, slots=True)
class KycRecordSummary:
    id: UUID
    party_id: UUID
    document_type: str
    document_reference: str | None
    evidence_document_id: UUID | None
    verification_status: str
    verified_by: UUID | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class PurchaseOrderCreate:
    project_id: UUID
    vendor_id: UUID
    budget_line_id: UUID | None
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class PurchaseOrderSummary:
    id: UUID
    project_id: UUID
    vendor_id: UUID
    budget_line_id: UUID | None
    total_amount: Decimal
    status: str
    issued_at: datetime | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class PurchaseOrderLineCreate:
    cost_code_id: UUID | None
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class PurchaseOrderLineSummary:
    id: UUID
    purchase_order_id: UUID
    cost_code_id: UUID | None
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ContractCreate:
    project_id: UUID
    party_id: UUID
    contract_type: str | None
    value: Decimal | None


@dataclass(frozen=True, slots=True)
class ContractSummary:
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


@dataclass(frozen=True, slots=True)
class ContractExecution:
    execution_method: str
    executed_document_id: UUID


@dataclass(frozen=True, slots=True)
class MilestoneCreate:
    description: str | None
    due_date: date | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class MilestoneSummary:
    id: UUID
    contract_id: UUID
    description: str | None
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class InsuranceCreate:
    project_id: UUID | None
    contract_id: UUID | None
    vendor_id: UUID | None
    policy_number: str
    insurer: str | None
    coverage_type: str
    sum_insured: Decimal | None
    valid_from: date | None
    valid_to: date | None


@dataclass(frozen=True, slots=True)
class InsuranceSummary:
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


@dataclass(frozen=True, slots=True)
class LabourComplianceCreate:
    contractor_id: UUID
    project_id: UUID | None
    pf_registration_number: str | None
    esi_registration_number: str | None
    contract_labour_licence_number: str | None
    minimum_wage_evidence_ref: str | None


@dataclass(frozen=True, slots=True)
class LabourComplianceSummary:
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
