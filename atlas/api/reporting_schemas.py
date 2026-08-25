"""Validated HTTP models for Phase 10 reporting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.reporting.schemas import ReportRequestCreate


class DtoResponse(BaseModel):
    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(**{f: getattr(value, f) for f in cls.model_fields})


class ProjectDashboardResponse(DtoResponse):
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


class EntityDashboardResponse(DtoResponse):
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


class ReportRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_type: str = Field(pattern="^(ceo_project_summary|ceo_entity_summary)$")
    output_format: str = Field(pattern="^(pdf|xlsx)$")
    project_id: UUID | None = None

    def to_dto(self, legal_entity_id: UUID) -> ReportRequestCreate:
        return ReportRequestCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class ReportRequestResponse(DtoResponse):
    id: UUID
    legal_entity_id: UUID
    project_id: UUID | None
    report_type: str
    output_format: str
    status: str
    requested_at: datetime
    version: int
