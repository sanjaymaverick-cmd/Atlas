"""ORM mappings for canonical Phase 5 construction and quality schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Numeric, String
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


class ScheduleActivity(AuditColumns, Base):
    __tablename__ = "schedule_activities"
    __table_args__ = {"schema": "construction"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    wbs_reference: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    predecessor_activity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String)


class SiteDiaryEntry(AuditColumns, Base):
    __tablename__ = "site_diary_entries"
    __table_args__ = {"schema": "construction"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    entry_date: Mapped[date] = mapped_column(Date)
    client_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    device_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weather: Mapped[str | None] = mapped_column(String)
    labour_strength: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    materials_received: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    materials_consumed: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    equipment_breakdowns: Mapped[str | None] = mapped_column(String)
    visitor_log: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    site_instructions: Mapped[str | None] = mapped_column(String)
    delays_and_reasons: Mapped[str | None] = mapped_column(String)
    recorded_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String)


class EhsIncident(AuditColumns, Base):
    __tablename__ = "ehs_incidents"
    __table_args__ = {"schema": "construction"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    site_diary_entry_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    incident_date: Mapped[date] = mapped_column(Date)
    severity: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    corrective_action: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class ProgressUpdate(AuditColumns, Base):
    __tablename__ = "progress_updates"
    __table_args__ = {"schema": "construction"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    schedule_activity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    progress_date: Mapped[date] = mapped_column(Date)
    percent_complete: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    notes: Mapped[str | None] = mapped_column(String)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class InspectionTemplate(AuditColumns, Base):
    __tablename__ = "inspection_templates"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    work_package: Mapped[str] = mapped_column(String)
    template_name: Mapped[str] = mapped_column(String)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String)


class Inspection(AuditColumns, Base):
    __tablename__ = "inspections"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    building_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    floor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    template_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    inspector_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    result: Mapped[str | None] = mapped_column(String)
    photos_ref: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class InspectionEvidence(Base):
    __tablename__ = "inspection_evidence"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    inspection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    evidence_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class SnagItem(AuditColumns, Base):
    __tablename__ = "snag_items"
    __table_args__ = {"schema": "quality"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    inspection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    building_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    floor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    assigned_to: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String)
