"""Published immutable Phase 6 DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BimImportCreate:
    project_id: UUID
    source_document_id: UUID


@dataclass(frozen=True, slots=True)
class BimImportSummary:
    id: UUID
    project_id: UUID
    source_document_id: UUID
    status: str
    validated_at: datetime | None
    validated_by: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class CostCodeCreate:
    project_id: UUID
    code: str
    description: str | None = None
    parent_cost_code_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CostCodeSummary:
    id: UUID
    project_id: UUID
    code: str
    description: str | None
    wbs_level: int
    parent_cost_code_id: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class QuantityCreate:
    project_id: UUID
    calculated_quantity: Decimal
    tolerance_pct: Decimal
    cost_code_id: UUID | None = None
    bim_object_id: UUID | None = None
    work_package: str | None = None


@dataclass(frozen=True, slots=True)
class QuantitySummary:
    id: UUID
    project_id: UUID
    calculated_quantity: Decimal | None
    verified_quantity: Decimal | None
    final_approved_quantity: Decimal | None
    tolerance_pct: Decimal
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class MaterialCreate:
    name: str
    unit_of_measure: str
    category: str | None = None


@dataclass(frozen=True, slots=True)
class MaterialSummary:
    id: UUID
    name: str
    unit_of_measure: str
    category: str | None
    version: int


@dataclass(frozen=True, slots=True)
class ReceiptCreate:
    project_id: UUID
    material_id: UUID
    quantity_received: Decimal
    received_date: date
    purchase_order_id: UUID | None = None
    batch_reference: str | None = None
    certificate_document_id: UUID | None = None
    status: str = "received"


@dataclass(frozen=True, slots=True)
class ReceiptSummary:
    id: UUID
    project_id: UUID
    material_id: UUID
    quantity_received: Decimal
    received_date: date
    status: str
    certificate_document_id: UUID | None
    version: int


@dataclass(frozen=True, slots=True)
class IssuanceCreate:
    quantity_issued: Decimal
    issued_date: date
    issued_to: str | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class IssuanceSummary:
    id: UUID
    project_id: UUID
    material_id: UUID
    material_receipt_id: UUID
    quantity_issued: Decimal
    issued_date: date
    evidence_document_id: UUID | None
    version: int
