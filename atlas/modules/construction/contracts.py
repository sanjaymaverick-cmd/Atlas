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
    MeetingActionCreate,
    MeetingActionSummary,
    MeetingCreate,
    MeetingSummary,
    ProgressCreate,
    ProgressSummary,
    ScheduleCreate,
    ScheduleSummary,
    SiteDiaryCreate,
    SiteDiarySummary,
    SnagCreate,
    SnagSummary,
    TemplateCreate,
    TemplateDraftSummary,
    TemplateSummary,
    TemplateUpdate,
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
    async def create_meeting(
        self, session: AsyncSession, *, actor_user_id: UUID, data: MeetingCreate
    ) -> MeetingSummary: ...
    async def create_meeting_action(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        meeting_id: UUID,
        data: MeetingActionCreate,
    ) -> MeetingActionSummary: ...
    async def transition_meeting_action(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        action_id: UUID,
        target_status: str,
    ) -> MeetingActionSummary: ...
    async def close_meeting(
        self, session: AsyncSession, *, actor_user_id: UUID, meeting_id: UUID
    ) -> MeetingSummary: ...
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
    async def update_template_draft(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        template_id: UUID,
        data: TemplateUpdate,
    ) -> TemplateDraftSummary: ...
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
    async def archive_activity(
        self, session: AsyncSession, *, actor_user_id: UUID, activity_id: UUID
    ) -> ScheduleSummary: ...
    async def archive_progress(
        self, session: AsyncSession, *, actor_user_id: UUID, progress_id: UUID
    ) -> ProgressSummary: ...
    async def archive_site_diary(
        self, session: AsyncSession, *, actor_user_id: UUID, diary_id: UUID
    ) -> SiteDiarySummary: ...
    async def archive_ehs_incident(
        self, session: AsyncSession, *, actor_user_id: UUID, incident_id: UUID
    ) -> EhsSummary: ...
    async def archive_template(
        self, session: AsyncSession, *, actor_user_id: UUID, template_id: UUID
    ) -> TemplateSummary: ...
    async def archive_inspection(
        self, session: AsyncSession, *, actor_user_id: UUID, inspection_id: UUID
    ) -> InspectionSummary: ...
    async def archive_snag(
        self, session: AsyncSession, *, actor_user_id: UUID, snag_id: UUID
    ) -> SnagSummary: ...
    async def archive_meeting(
        self, session: AsyncSession, *, actor_user_id: UUID, meeting_id: UUID
    ) -> MeetingSummary: ...
    async def archive_meeting_action(
        self, session: AsyncSession, *, actor_user_id: UUID, action_id: UUID
    ) -> MeetingActionSummary: ...
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
    async def get_inspection_for_reference(
        self, session: AsyncSession, *, actor_user_id: UUID, inspection_id: UUID
    ) -> InspectionSummary: ...
    async def list_snags(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[SnagSummary]: ...
    async def list_meetings(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[MeetingSummary]: ...
    async def list_meeting_actions(
        self, session: AsyncSession, *, actor_user_id: UUID, meeting_id: UUID
    ) -> list[MeetingActionSummary]: ...
    async def list_template_drafts(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[TemplateDraftSummary]: ...
