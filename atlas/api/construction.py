"""Thin HTTP adapters for Phase 5 construction and quality workflows."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.construction_schemas import (
    EhsCreateRequest,
    EhsResponse,
    InspectionCompletionRequest,
    InspectionCreateRequest,
    InspectionResponse,
    MeetingActionCreateRequest,
    MeetingActionResponse,
    MeetingCreateRequest,
    MeetingResponse,
    ProgressCreateRequest,
    ProgressResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    SiteDiaryCreateRequest,
    SiteDiaryResponse,
    SnagCreateRequest,
    SnagResponse,
    TemplateCreateRequest,
    TemplateDraftResponse,
    TemplateResponse,
    TemplateUpdateRequest,
    TransitionRequest,
)
from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["construction", "quality"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


def response(model: type[BaseModel], value: Any) -> BaseModel:
    return model(**{field: getattr(value, field) for field in model.model_fields})


@router.post(
    "/projects/{project_id}/schedule-activities",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    project_id: UUID, body: ScheduleCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        ScheduleResponse,
        await services.construction.create_activity(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post("/schedule-activities/{activity_id}/transition", response_model=ScheduleResponse)
async def transition_activity(
    activity_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        ScheduleResponse,
        await services.construction.transition_activity(
            session,
            actor_user_id=actor.user_id,
            activity_id=activity_id,
            target_status=body.target_status,
        ),
    )


@router.post(
    "/schedule-activities/{activity_id}/progress",
    response_model=ProgressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_progress(
    activity_id: UUID, body: ProgressCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        ProgressResponse,
        await services.construction.add_progress(
            session, actor_user_id=actor.user_id, activity_id=activity_id, data=body.to_dto()
        ),
    )


@router.post(
    "/projects/{project_id}/site-diary",
    response_model=SiteDiaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_diary(
    project_id: UUID, body: SiteDiaryCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        SiteDiaryResponse,
        await services.construction.submit_site_diary(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post(
    "/projects/{project_id}/meetings",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting(
    project_id: UUID, body: MeetingCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        MeetingResponse,
        await services.construction.create_meeting(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post(
    "/meetings/{meeting_id}/actions",
    response_model=MeetingActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting_action(
    meeting_id: UUID,
    body: MeetingActionCreateRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> BaseModel:
    return response(
        MeetingActionResponse,
        await services.construction.create_meeting_action(
            session,
            actor_user_id=actor.user_id,
            meeting_id=meeting_id,
            data=body.to_dto(),
        ),
    )


@router.post("/meeting-actions/{action_id}/transition", response_model=MeetingActionResponse)
async def transition_meeting_action(
    action_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        MeetingActionResponse,
        await services.construction.transition_meeting_action(
            session,
            actor_user_id=actor.user_id,
            action_id=action_id,
            target_status=body.target_status,
        ),
    )


@router.post("/meetings/{meeting_id}/close", response_model=MeetingResponse)
async def close_meeting(
    meeting_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        MeetingResponse,
        await services.construction.close_meeting(
            session, actor_user_id=actor.user_id, meeting_id=meeting_id
        ),
    )


@router.post(
    "/projects/{project_id}/ehs-incidents",
    response_model=EhsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ehs(
    project_id: UUID, body: EhsCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        EhsResponse,
        await services.construction.create_ehs_incident(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post("/ehs-incidents/{incident_id}/transition", response_model=EhsResponse)
async def transition_ehs(
    incident_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        EhsResponse,
        await services.construction.transition_ehs_incident(
            session,
            actor_user_id=actor.user_id,
            incident_id=incident_id,
            target_status=body.target_status,
            corrective_action=body.corrective_action,
        ),
    )


@router.post(
    "/inspection-templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_template(
    body: TemplateCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        TemplateResponse,
        await services.construction.create_template(
            session, actor_user_id=actor.user_id, data=body.to_dto()
        ),
    )


@router.post("/inspection-templates/{template_id}/transition", response_model=TemplateResponse)
async def transition_template(
    template_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        TemplateResponse,
        await services.construction.transition_template(
            session,
            actor_user_id=actor.user_id,
            template_id=template_id,
            target_status=body.target_status,
        ),
    )


@router.put("/inspection-templates/{template_id}", response_model=TemplateDraftResponse)
async def update_template_draft(
    template_id: UUID,
    body: TemplateUpdateRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> BaseModel:
    return response(
        TemplateDraftResponse,
        await services.construction.update_template_draft(
            session,
            actor_user_id=actor.user_id,
            template_id=template_id,
            data=body.to_dto(),
        ),
    )


@router.post(
    "/projects/{project_id}/inspections",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_inspection(
    project_id: UUID, body: InspectionCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        InspectionResponse,
        await services.construction.schedule_inspection(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post("/inspections/{inspection_id}/complete", response_model=InspectionResponse)
async def complete_inspection(
    inspection_id: UUID,
    body: InspectionCompletionRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> BaseModel:
    return response(
        InspectionResponse,
        await services.construction.complete_inspection(
            session, actor_user_id=actor.user_id, inspection_id=inspection_id, data=body.to_dto()
        ),
    )


@router.post(
    "/projects/{project_id}/snags", response_model=SnagResponse, status_code=status.HTTP_201_CREATED
)
async def create_snag(
    project_id: UUID, body: SnagCreateRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        SnagResponse,
        await services.construction.create_snag(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        ),
    )


@router.post("/snags/{snag_id}/transition", response_model=SnagResponse)
async def transition_snag(
    snag_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        SnagResponse,
        await services.construction.transition_snag(
            session, actor_user_id=actor.user_id, snag_id=snag_id, target_status=body.target_status
        ),
    )


@router.post("/schedule-activities/{activity_id}/archive", response_model=ScheduleResponse)
async def archive_activity(
    activity_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        ScheduleResponse,
        await services.construction.archive_activity(
            session, actor_user_id=actor.user_id, activity_id=activity_id
        ),
    )


@router.post("/progress-updates/{progress_id}/archive", response_model=ProgressResponse)
async def archive_progress(
    progress_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        ProgressResponse,
        await services.construction.archive_progress(
            session, actor_user_id=actor.user_id, progress_id=progress_id
        ),
    )


@router.post("/site-diary/{diary_id}/archive", response_model=SiteDiaryResponse)
async def archive_site_diary(
    diary_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        SiteDiaryResponse,
        await services.construction.archive_site_diary(
            session, actor_user_id=actor.user_id, diary_id=diary_id
        ),
    )


@router.post("/ehs-incidents/{incident_id}/archive", response_model=EhsResponse)
async def archive_ehs_incident(
    incident_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        EhsResponse,
        await services.construction.archive_ehs_incident(
            session, actor_user_id=actor.user_id, incident_id=incident_id
        ),
    )


@router.post("/inspection-templates/{template_id}/archive", response_model=TemplateResponse)
async def archive_template(
    template_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        TemplateResponse,
        await services.construction.archive_template(
            session, actor_user_id=actor.user_id, template_id=template_id
        ),
    )


@router.post("/inspections/{inspection_id}/archive", response_model=InspectionResponse)
async def archive_inspection(
    inspection_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        InspectionResponse,
        await services.construction.archive_inspection(
            session, actor_user_id=actor.user_id, inspection_id=inspection_id
        ),
    )


@router.post("/snags/{snag_id}/archive", response_model=SnagResponse)
async def archive_snag(snag_id: UUID, actor: Actor, session: Db, services: Services) -> BaseModel:
    return response(
        SnagResponse,
        await services.construction.archive_snag(
            session, actor_user_id=actor.user_id, snag_id=snag_id
        ),
    )


@router.post("/meetings/{meeting_id}/archive", response_model=MeetingResponse)
async def archive_meeting(
    meeting_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        MeetingResponse,
        await services.construction.archive_meeting(
            session, actor_user_id=actor.user_id, meeting_id=meeting_id
        ),
    )


@router.post("/meeting-actions/{action_id}/archive", response_model=MeetingActionResponse)
async def archive_meeting_action(
    action_id: UUID, actor: Actor, session: Db, services: Services
) -> BaseModel:
    return response(
        MeetingActionResponse,
        await services.construction.archive_meeting_action(
            session, actor_user_id=actor.user_id, action_id=action_id
        ),
    )


# `response_model` takes a runtime value, but these schemas are created at
# runtime by `response_model()` rather than declared as classes, so mypy cannot
# read them as types — and `list[X]` is a type expression. Subscripting through
# `__class_getitem__` builds the same object without writing a type expression,
# which keeps the OpenAPI schema exact and strict mypy quiet.
def _list_of(model: Any) -> Any:
    return list.__class_getitem__(model)


ScheduleListResponse = _list_of(ScheduleResponse)
SiteDiaryListResponse = _list_of(SiteDiaryResponse)
EhsListResponse = _list_of(EhsResponse)
InspectionListResponse = _list_of(InspectionResponse)
SnagListResponse = _list_of(SnagResponse)
MeetingListResponse = _list_of(MeetingResponse)
MeetingActionListResponse = _list_of(MeetingActionResponse)
TemplateDraftListResponse = _list_of(TemplateDraftResponse)


# -- reads ------------------------------------------------------------------
# Added 2026-08-20; this router previously exposed writes only. The response
# models here are built by `response_model`, so they are runtime values rather
# than types — hence the `-> list[BaseModel]` annotations and the shared
# `response` helper, matching the write routes above.


@router.get("/projects/{project_id}/schedule-activities", response_model=ScheduleListResponse)
async def list_activities(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_activities(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(ScheduleResponse, row) for row in rows]


@router.get("/projects/{project_id}/site-diary", response_model=SiteDiaryListResponse)
async def list_diary(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_diary_entries(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(SiteDiaryResponse, row) for row in rows]


@router.get("/projects/{project_id}/ehs-incidents", response_model=EhsListResponse)
async def list_ehs(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_ehs_incidents(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(EhsResponse, row) for row in rows]


@router.get("/projects/{project_id}/inspections", response_model=InspectionListResponse)
async def list_inspections(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_inspections(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(InspectionResponse, row) for row in rows]


@router.get("/projects/{project_id}/snags", response_model=SnagListResponse)
async def list_snags(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_snags(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(SnagResponse, row) for row in rows]


@router.get("/projects/{project_id}/meetings", response_model=MeetingListResponse)
async def list_meetings(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_meetings(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(MeetingResponse, row) for row in rows]


@router.get("/meetings/{meeting_id}/actions", response_model=MeetingActionListResponse)
async def list_meeting_actions(
    meeting_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_meeting_actions(
        session, actor_user_id=actor.user_id, meeting_id=meeting_id
    )
    return [response(MeetingActionResponse, row) for row in rows]


@router.get(
    "/projects/{project_id}/inspection-template-drafts",
    response_model=TemplateDraftListResponse,
)
async def list_template_drafts(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BaseModel]:
    rows = await services.construction.list_template_drafts(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [response(TemplateDraftResponse, row) for row in rows]
