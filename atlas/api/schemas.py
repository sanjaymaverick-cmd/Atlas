"""HTTP request and response models."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.organization.schemas import ProjectCreate, ProjectSummary, ProjectUpdate


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    code: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    status: str = Field(default="planning", min_length=1, max_length=100)
    start_date: date | None = None
    target_completion_date: date | None = None

    def to_dto(self, legal_entity_id: UUID) -> ProjectCreate:
        return ProjectCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, min_length=1, max_length=100)
    start_date: date | None = None
    target_completion_date: date | None = None

    def to_dto(self) -> ProjectUpdate:
        return ProjectUpdate(**self.model_dump())


class ProjectResponse(BaseModel):
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

    @classmethod
    def from_dto(cls, project: ProjectSummary) -> ProjectResponse:
        return cls(**{field: getattr(project, field) for field in cls.model_fields})
