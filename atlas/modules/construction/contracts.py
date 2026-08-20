"""Published Phase 5 construction contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.construction.schemas import (
    EhsCreate,
    EhsSummary,
    InspectionCompletion,
    InspectionCreate,
    InspectionSummary,
    ProgressCreate,
    ProgressSummary,
    ScheduleCreate,
    ScheduleSummary,
    SiteDiaryCreate,
    SiteDiarySummary,
    SnagCreate,
    SnagSummary,
    TemplateCreate,
    TemplateSummary,
)


class ConstructionNotAuthorisedError(Exception):
    pass


class ConstructionNotFoundError(Exception):
    pass


class ConstructionConflictError(Exception):
    pass


class ConstructionContract(Protocol):
    async def create_activity(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ScheduleCreate
    ) -> ScheduleSummary: ...
    async def transition_activity(
        self, session: AsyncSession, *, actor_user_id: UUID, activity_id: UUID, target_status: str
    ) -> ScheduleSummary: ...
    async def add_progress(
        self, session: AsyncSession, *, actor_user_id: UUID, activity_id: UUID, data: ProgressCreate
    ) -> ProgressSummary: ...
    async def submit_site_diary(
        self, session: AsyncSession, *, actor_user_id: UUID, data: SiteDiaryCreate
    ) -> SiteDiarySummary: ...
    async def create_ehs_incident(
        self, session: AsyncSession, *, actor_user_id: UUID, data: EhsCreate
    ) -> EhsSummary: ...
    async def transition_ehs_incident(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        incident_id: UUID,
        target_status: str,
        corrective_action: str | None = None,
    ) -> EhsSummary: ...
    async def create_template(
        self, session: AsyncSession, *, actor_user_id: UUID, data: TemplateCreate
    ) -> TemplateSummary: ...
    async def transition_template(
        self, session: AsyncSession, *, actor_user_id: UUID, template_id: UUID, target_status: str
    ) -> TemplateSummary: ...
    async def schedule_inspection(
        self, session: AsyncSession, *, actor_user_id: UUID, data: InspectionCreate
    ) -> InspectionSummary: ...
    async def complete_inspection(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        inspection_id: UUID,
        data: InspectionCompletion,
    ) -> InspectionSummary: ...
    async def create_snag(
        self, session: AsyncSession, *, actor_user_id: UUID, data: SnagCreate
    ) -> SnagSummary: ...
    async def transition_snag(
        self, session: AsyncSession, *, actor_user_id: UUID, snag_id: UUID, target_status: str
    ) -> SnagSummary: ...
    async def list_activities(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ScheduleSummary]: ...
    async def list_diary_entries(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[SiteDiarySummary]: ...
    async def list_ehs_incidents(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[EhsSummary]: ...
    async def list_inspections(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[InspectionSummary]: ...
    async def list_snags(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[SnagSummary]: ...
