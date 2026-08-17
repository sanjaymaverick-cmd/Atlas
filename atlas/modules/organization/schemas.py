"""Organization DTOs — the module's published surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LegalEntitySummary:
    id: UUID
    business_group_id: UUID
    name: str
    registration_number: str | None
    entity_type: str | None
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    id: UUID
    legal_entity_id: UUID
    name: str
    code: str
    city: str | None
    status: str
    start_date: date | None
    target_completion_date: date | None
    version: int
    archived_at: datetime | None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass(frozen=True, slots=True)
class ProjectCreate:
    legal_entity_id: UUID
    name: str
    code: str
    city: str | None = None
    status: str = "planning"
    start_date: date | None = None
    target_completion_date: date | None = None


@dataclass(frozen=True, slots=True)
class ProjectUpdate:
    """Fields that may be changed. ``None`` means "leave alone".

    ``legal_entity_id`` is absent deliberately: moving a project between legal
    entities would silently move every cost, contract and approval scoped to it
    across a separation boundary Blueprint §2 treats as hard. If that is ever
    needed it should be an explicit, separately-authorised operation with its
    own audit action, not a field on a general update.
    """

    name: str | None = None
    code: str | None = None
    city: str | None = None
    status: str | None = None
    start_date: date | None = None
    target_completion_date: date | None = None
