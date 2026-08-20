"""Published DTOs for statutory registrations and obligations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReraRegistrationCreate:
    project_id: UUID
    registration_number: str
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(frozen=True, slots=True)
class ReraRegistrationSummary:
    id: UUID
    project_id: UUID
    registration_number: str
    valid_from: date | None
    valid_to: date | None
    status: str
    version: int
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ComplianceObligationCreate:
    legal_entity_id: UUID | None
    project_id: UUID | None
    obligation_type: str
    authority: str | None = None
    due_date: date | None = None
    amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ComplianceObligationSummary:
    id: UUID
    legal_entity_id: UUID | None
    project_id: UUID | None
    obligation_type: str
    authority: str | None
    due_date: date | None
    amount: Decimal | None
    status: str
    version: int
    archived_at: datetime | None
