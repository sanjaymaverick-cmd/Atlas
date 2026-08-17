"""Mappings for Phase 10 reporting views and report requests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class ProjectSummaryView(Base):
    __tablename__ = "mv_ceo_project_summary"
    __table_args__ = {"schema": "reporting"}
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    committed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    approved_po_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    released_payment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    allocated_collection_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    outstanding_receivable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unallocated_collection_count: Mapped[int]
    overdue_installment_count: Mapped[int]
    delayed_activity_count: Mapped[int]
    failed_inspection_count: Mapped[int]
    open_compliance_count: Mapped[int]
    open_reconciliation_count: Mapped[int]
    total_unit_count: Mapped[int]
    available_unit_count: Mapped[int]
    committed_unit_count: Mapped[int]
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportRequest(Base):
    __tablename__ = "report_requests"
    __table_args__ = {"schema": "reporting"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    report_type: Mapped[str]
    output_format: Mapped[str]
    status: Mapped[str]
    output_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
