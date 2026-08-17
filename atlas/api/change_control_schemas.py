"""Validated HTTP models for Phase 7 workflows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.change_control.schemas import (
    ChangeCreate,
    DiscrepancyCreate,
    DiscrepancyTransition,
    NcrCreate,
    NcrTransition,
    RfiCreate,
    RfiResponse,
)


class DtoResponse(BaseModel):
    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(**{f: getattr(value, f) for f in cls.model_fields})


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=60)


class ChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=8000)
    schedule_impact: str | None = Field(default=None, max_length=4000)
    budget_impact: Decimal | None = Field(default=None, ge=0)
    evidence_document_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> ChangeCreate:
        return ChangeCreate(project_id=project_id, **self.model_dump())


class ChangeResponse(DtoResponse):
    id: UUID
    project_id: UUID
    status: str
    evidence_document_id: UUID | None
    decided_by: UUID | None
    decided_at: datetime | None
    version: int


class RfiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=8000)
    routed_to: UUID | None = None
    sla_due_at: datetime | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> RfiCreate:
        return RfiCreate(project_id=project_id, **self.model_dump())


class RfiResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str = Field(min_length=1, max_length=8000)
    evidence_document_id: UUID | None = None

    def to_dto(self) -> RfiResponse:
        return RfiResponse(**self.model_dump())


class RfiSummaryResponse(DtoResponse):
    id: UUID
    project_id: UUID
    routed_to: UUID | None
    sla_due_at: datetime | None
    status: str
    responded_by: UUID | None
    responded_at: datetime | None
    version: int


class NcrRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: str = Field(pattern="^(minor|major|critical)$")
    description: str = Field(min_length=1, max_length=8000)
    inspection_id: UUID | None = None
    schedule_activity_id: UUID | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> NcrCreate:
        return NcrCreate(project_id=project_id, **self.model_dump())


class NcrTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=60)
    corrective_action: str | None = Field(default=None, max_length=8000)
    reinspection_id: UUID | None = None
    evidence_document_id: UUID | None = None

    def to_dto(self) -> NcrTransition:
        return NcrTransition(**self.model_dump())


class NcrResponse(DtoResponse):
    id: UUID
    project_id: UUID
    severity: str
    status: str
    evidence_document_id: UUID | None
    reinspection_id: UUID | None
    closed_by: UUID | None
    closed_at: datetime | None
    version: int


class DiscrepancyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_item_id: UUID
    description: str | None = Field(default=None, max_length=8000)
    evidence_document_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> DiscrepancyCreate:
        return DiscrepancyCreate(project_id=project_id, **self.model_dump())


class DiscrepancyTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=60)
    proposed_resolution: str | None = Field(default=None, max_length=8000)
    evidence_document_id: UUID | None = None

    def to_dto(self) -> DiscrepancyTransition:
        return DiscrepancyTransition(**self.model_dump())


class DiscrepancyResponse(DtoResponse):
    id: UUID
    project_id: UUID
    quantity_item_id: UUID | None
    status: str
    evidence_document_id: UUID | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    version: int
