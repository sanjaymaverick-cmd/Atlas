"""Thin HTTP adapters for Phase 10 reporting."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import (
    ApiServices,
    get_current_session,
    get_reporting_session,
    get_services,
    get_session,
)
from atlas.api.reporting_schemas import (
    EntityDashboardResponse,
    ProjectDashboardResponse,
    ReportRequestBody,
    ReportRequestResponse,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["reporting"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Primary = Annotated[AsyncSession, Depends(get_session)]
Reporting = Annotated[AsyncSession, Depends(get_reporting_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.get("/projects/{project_id}/dashboard", response_model=ProjectDashboardResponse)
async def project_dashboard(
    project_id: UUID, actor: Actor, primary: Primary, reporting: Reporting, services: Services
) -> ProjectDashboardResponse:
    return ProjectDashboardResponse.from_dto(
        await services.reporting.get_project_dashboard(
            primary, reporting, actor_user_id=actor.user_id, project_id=project_id
        )
    )


@router.get("/legal-entities/{legal_entity_id}/dashboard", response_model=EntityDashboardResponse)
async def entity_dashboard(
    legal_entity_id: UUID, actor: Actor, primary: Primary, reporting: Reporting, services: Services
) -> EntityDashboardResponse:
    return EntityDashboardResponse.from_dto(
        await services.reporting.get_entity_dashboard(
            primary, reporting, actor_user_id=actor.user_id, legal_entity_id=legal_entity_id
        )
    )


@router.post(
    "/legal-entities/{legal_entity_id}/report-requests",
    response_model=ReportRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_report(
    legal_entity_id: UUID,
    body: ReportRequestBody,
    actor: Actor,
    primary: Primary,
    reporting: Reporting,
    services: Services,
) -> ReportRequestResponse:
    return ReportRequestResponse.from_dto(
        await services.reporting.create_report_request(
            primary, reporting, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
        )
    )
