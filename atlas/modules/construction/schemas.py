"""Published DTOs for Phase 5 construction and quality workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScheduleCreate:
    project_id: UUID
    name: str
    wbs_reference: UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    predecessor_activity_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ScheduleSummary:
    id: UUID
    project_id: UUID
    name: str
    planned_start: date | None
    planned_end: date | None
    actual_start: date | None
    actual_end: date | None
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class MaterialMovement:
    material_id: UUID
    quantity: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class SiteDiaryCreate:
    project_id: UUID
    entry_date: date
    client_record_id: UUID
    device_recorded_at: datetime | None
    weather: str | None
    labour_strength: dict[str, int]
    materials_received: tuple[MaterialMovement, ...]
    materials_consumed: tuple[MaterialMovement, ...]
    equipment_breakdowns: str | None
    visitor_count: int
    site_instructions: str | None
    delays_and_reasons: str | None


@dataclass(frozen=True, slots=True)
class SiteDiarySummary:
    id: UUID
    project_id: UUID
    entry_date: date
    client_record_id: UUID
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProgressCreate:
    progress_date: date
    percent_complete: Decimal
    notes: str | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProgressSummary:
    id: UUID
    project_id: UUID
    schedule_activity_id: UUID
    progress_date: date
    percent_complete: Decimal
    evidence_document_id: UUID | None
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class EhsCreate:
    project_id: UUID
    incident_date: date
    severity: str
    site_diary_entry_id: UUID | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EhsSummary:
    id: UUID
    project_id: UUID
    incident_date: date
    severity: str
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    item: str
    requires_evidence: bool = False


@dataclass(frozen=True, slots=True)
class TemplateCreate:
    project_id: UUID | None
    work_package: str
    template_name: str
    checklist: tuple[ChecklistItem, ...]


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    id: UUID
    project_id: UUID | None
    work_package: str
    template_name: str
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class InspectionCreate:
    project_id: UUID
    template_id: UUID | None
    inspector_id: UUID | None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InspectionSummary:
    id: UUID
    project_id: UUID
    template_id: UUID | None
    inspector_id: UUID | None
    result: str | None
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class InspectionCompletion:
    result: str
    notes: str | None
    evidence_document_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SnagCreate:
    project_id: UUID
    description: str
    severity: str
    inspection_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SnagSummary:
    id: UUID
    project_id: UUID
    description: str
    severity: str
    assigned_to: UUID | None
    due_date: date | None
    evidence_document_id: UUID | None
    status: str
    version: int
    archived_at: datetime | None
