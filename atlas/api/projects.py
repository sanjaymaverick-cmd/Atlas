"""Thin HTTP adapter for Organization project operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.schemas import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ProjectResponse:
    project = await services.organization.get_project(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return ProjectResponse.from_dto(project)


@router.get("/legal-entities/{legal_entity_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    legal_entity_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[ProjectResponse]:
    projects = await services.organization.list_projects(
        session, actor_user_id=actor.user_id, legal_entity_id=legal_entity_id
    )
    return [ProjectResponse.from_dto(project) for project in projects]


@router.post(
    "/legal-entities/{legal_entity_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    legal_entity_id: UUID,
    body: ProjectCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ProjectResponse:
    project = await services.organization.create_project(
        session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
    )
    return ProjectResponse.from_dto(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ProjectResponse:
    project = await services.organization.update_project(
        session, actor_user_id=actor.user_id, project_id=project_id, data=body.to_dto()
    )
    return ProjectResponse.from_dto(project)


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ProjectResponse:
    project = await services.organization.archive_project(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return ProjectResponse.from_dto(project)
