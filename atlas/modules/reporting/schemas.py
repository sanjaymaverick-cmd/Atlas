"""Published immutable Phase 10 reporting DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProjectDashboard:
    project_id: UUID
    legal_entity_id: UUID
    planned_amount: Decimal
    committed_amount: Decimal
    actual_amount: Decimal
    approved_po_amount: Decimal
    released_payment_amount: Decimal
    allocated_collection_amount: Decimal
    outstanding_receivable_amount: Decimal
    unallocated_collection_count: int
    overdue_installment_count: int
    delayed_activity_count: int
    failed_inspection_count: int
    open_compliance_count: int
    open_reconciliation_count: int
    total_unit_count: int
    available_unit_count: int
    committed_unit_count: int
    refreshed_at: datetime


@dataclass(frozen=True, slots=True)
class EntityDashboard:
    legal_entity_id: UUID
    project_count: int
    planned_amount: Decimal
    committed_amount: Decimal
    actual_amount: Decimal
    released_payment_amount: Decimal
    allocated_collection_amount: Decimal
    outstanding_receivable_amount: Decimal
    delayed_activity_count: int
    failed_inspection_count: int
    open_compliance_count: int
    available_unit_count: int
    refreshed_at: datetime


@dataclass(frozen=True, slots=True)
class ReportRequestCreate:
    legal_entity_id: UUID
    report_type: str
    output_format: str
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ReportRequestSummary:
    id: UUID
    legal_entity_id: UUID
    project_id: UUID | None
    report_type: str
    output_format: str
    status: str
    requested_at: datetime
    version: int
