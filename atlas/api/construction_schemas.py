"""Validated HTTP models for Phase 5 construction and quality APIs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.construction.schemas import (
    ChecklistItem,
    EhsCreate,
    InspectionCompletion,
    InspectionCreate,
    MaterialMovement,
    ProgressCreate,
    ScheduleCreate,
    SiteDiaryCreate,
    SnagCreate,
    TemplateCreate,
)


def dto_fields(model: type[BaseModel], value: Any) -> dict[str, Any]:
    return {field: getattr(value, field) for field in model.model_fields}


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=50)
    corrective_action: str | None = Field(default=None, max_length=4000)


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    wbs_reference: UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    predecessor_activity_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> ScheduleCreate:
        return ScheduleCreate(project_id=project_id, **self.model_dump())


class MaterialMovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=50)

    def to_dto(self) -> MaterialMovement:
        return MaterialMovement(**self.model_dump())


class SiteDiaryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_date: date
    client_record_id: UUID
    device_recorded_at: datetime | None = None
    weather: str | None = Field(default=None, max_length=500)
    labour_strength: dict[str, int] = Field(default_factory=dict)
    materials_received: list[MaterialMovementRequest] = Field(default_factory=list)
    materials_consumed: list[MaterialMovementRequest] = Field(default_factory=list)
    equipment_breakdowns: str | None = Field(default=None, max_length=4000)
    visitor_count: int = Field(default=0, ge=0)
    site_instructions: str | None = Field(default=None, max_length=4000)
    delays_and_reasons: str | None = Field(default=None, max_length=4000)

    def to_dto(self, project_id: UUID) -> SiteDiaryCreate:
        values = self.model_dump(exclude={"materials_received", "materials_consumed"})
        return SiteDiaryCreate(
            project_id=project_id,
            materials_received=tuple(v.to_dto() for v in self.materials_received),
            materials_consumed=tuple(v.to_dto() for v in self.materials_consumed),
            **values,
        )


class ProgressCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    progress_date: date
    percent_complete: Decimal = Field(ge=0, le=100)
    notes: str | None = Field(default=None, max_length=4000)
    evidence_document_id: UUID | None = None

    def to_dto(self) -> ProgressCreate:
        return ProgressCreate(**self.model_dump())


class EhsCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_date: date
    severity: str = Field(pattern="^(minor|major|fatal)$")
    site_diary_entry_id: UUID | None = None
    description: str | None = Field(default=None, max_length=8000)

    def to_dto(self, project_id: UUID) -> EhsCreate:
        return EhsCreate(project_id=project_id, **self.model_dump())


class ChecklistItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1, max_length=500)
    requires_evidence: bool = False


class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID | None = None
    work_package: str = Field(min_length=1, max_length=200)
    template_name: str = Field(min_length=1, max_length=300)
    checklist: list[ChecklistItemRequest] = Field(min_length=1, max_length=200)

    def to_dto(self) -> TemplateCreate:
        return TemplateCreate(
            self.project_id,
            self.work_package,
            self.template_name,
            tuple(ChecklistItem(v.item, v.requires_evidence) for v in self.checklist),
        )


class InspectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: UUID | None = None
    inspector_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> InspectionCreate:
        return InspectionCreate(project_id=project_id, **self.model_dump())


class InspectionCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str = Field(pattern="^(pass|fail)$")
    notes: str | None = Field(default=None, max_length=4000)
    evidence_document_ids: list[UUID] = Field(default_factory=list, max_length=50)

    def to_dto(self) -> InspectionCompletion:
        return InspectionCompletion(self.result, self.notes, tuple(self.evidence_document_ids))


class SnagCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=4000)
    severity: str = Field(pattern="^(minor|major|critical)$")
    inspection_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> SnagCreate:
        return SnagCreate(project_id=project_id, **self.model_dump())


def response_model(name: str, fields: dict[str, tuple[Any, Any]]) -> type[BaseModel]:
    from pydantic import create_model

    return cast(type[BaseModel], create_model(name, **fields))  # type: ignore[call-overload]


AuditFields = {"version": (int, ...), "archived_at": (datetime | None, ...)}
ScheduleResponse = response_model(
    "ScheduleResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "name": (str, ...),
        "planned_start": (date | None, ...),
        "planned_end": (date | None, ...),
        "actual_start": (date | None, ...),
        "actual_end": (date | None, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
SiteDiaryResponse = response_model(
    "SiteDiaryResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "entry_date": (date, ...),
        "client_record_id": (UUID, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
ProgressResponse = response_model(
    "ProgressResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "schedule_activity_id": (UUID, ...),
        "progress_date": (date, ...),
        "percent_complete": (Decimal, ...),
        "evidence_document_id": (UUID | None, ...),
        **AuditFields,
    },
)
EhsResponse = response_model(
    "EhsResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "incident_date": (date, ...),
        "severity": (str, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
TemplateResponse = response_model(
    "TemplateResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID | None, ...),
        "work_package": (str, ...),
        "template_name": (str, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
InspectionResponse = response_model(
    "InspectionResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "template_id": (UUID | None, ...),
        "inspector_id": (UUID | None, ...),
        "result": (str | None, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
SnagResponse = response_model(
    "SnagResponse",
    {
        "id": (UUID, ...),
        "project_id": (UUID, ...),
        "description": (str, ...),
        "severity": (str, ...),
        "assigned_to": (UUID | None, ...),
        "due_date": (date | None, ...),
        "evidence_document_id": (UUID | None, ...),
        "status": (str, ...),
        **AuditFields,
    },
)
