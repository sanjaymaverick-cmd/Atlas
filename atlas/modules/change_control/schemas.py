"""Published immutable Phase 7 DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ChangeCreate:
    project_id: UUID
    description: str
    schedule_impact: str | None = None
    budget_impact: Decimal | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ChangeSummary:
    id: UUID
    project_id: UUID
    status: str
    evidence_document_id: UUID | None
    decided_by: UUID | None
    decided_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class RfiCreate:
    project_id: UUID
    question: str
    routed_to: UUID | None
    sla_due_at: datetime | None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RfiResponse:
    response: str
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RfiSummary:
    id: UUID
    project_id: UUID
    routed_to: UUID | None
    sla_due_at: datetime | None
    status: str
    responded_by: UUID | None
    responded_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class NcrCreate:
    project_id: UUID
    severity: str
    description: str
    inspection_id: UUID | None = None
    schedule_activity_id: UUID | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class NcrTransition:
    target_status: str
    corrective_action: str | None = None
    reinspection_id: UUID | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class NcrSummary:
    id: UUID
    project_id: UUID
    severity: str
    status: str
    evidence_document_id: UUID | None
    reinspection_id: UUID | None
    closed_by: UUID | None
    closed_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class DiscrepancyCreate:
    project_id: UUID
    quantity_item_id: UUID
    description: str | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DiscrepancyTransition:
    target_status: str
    proposed_resolution: str | None = None
    evidence_document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DiscrepancySummary:
    id: UUID
    project_id: UUID
    quantity_item_id: UUID | None
    status: str
    evidence_document_id: UUID | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    version: int
