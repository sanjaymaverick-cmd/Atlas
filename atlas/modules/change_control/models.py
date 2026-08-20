"""ORM mappings onto canonical Phase 7 schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeRequest(AuditColumns, Base):
    __tablename__ = "change_requests"
    __table_args__ = {"schema": "construction"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str]
    schedule_impact: Mapped[str | None]
    budget_impact: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    requested_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]


class Rfi(AuditColumns, Base):
    __tablename__ = "rfis"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    raised_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    routed_to: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    question: Mapped[str]
    response: Mapped[str | None]
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    responded_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]


class Ncr(AuditColumns, Base):
    __tablename__ = "ncrs"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    inspection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    schedule_activity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    severity: Mapped[str]
    description: Mapped[str]
    corrective_action: Mapped[str | None]
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reinspection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    closed_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]


class DiscrepancyCase(AuditColumns, Base):
    __tablename__ = "discrepancy_cases"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    quantity_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None]
    evidence_ref: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    proposed_resolution: Mapped[str | None]
    resolved_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]
