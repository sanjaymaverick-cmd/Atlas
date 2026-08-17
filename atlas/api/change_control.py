"""Thin HTTP adapters for Phase 7 workflows."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.change_control_schemas import (
    ChangeRequest,
    ChangeResponse,
    DiscrepancyRequest,
    DiscrepancyResponse,
    DiscrepancyTransitionRequest,
    NcrRequest,
    NcrResponse,
    NcrTransitionRequest,
    RfiRequest,
    RfiResponseRequest,
    RfiSummaryResponse,
    TransitionRequest,
)
from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["change-control"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post(
    "/projects/{project_id}/change-requests",
    response_model=ChangeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_change(
    project_id: UUID, body: ChangeRequest, actor: Actor, session: Db, services: Services
) -> ChangeResponse:
    return ChangeResponse.from_dto(
        await services.change_control.create_change(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/change-requests/{change_id}/transition", response_model=ChangeResponse)
async def transition_change(
    change_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> ChangeResponse:
    return ChangeResponse.from_dto(
        await services.change_control.transition_change(
            session,
            actor_user_id=actor.user_id,
            change_id=change_id,
            target_status=body.target_status,
        )
    )


@router.post(
    "/projects/{project_id}/rfis",
    response_model=RfiSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rfi(
    project_id: UUID, body: RfiRequest, actor: Actor, session: Db, services: Services
) -> RfiSummaryResponse:
    return RfiSummaryResponse.from_dto(
        await services.change_control.create_rfi(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/rfis/{rfi_id}/respond", response_model=RfiSummaryResponse)
async def respond_rfi(
    rfi_id: UUID, body: RfiResponseRequest, actor: Actor, session: Db, services: Services
) -> RfiSummaryResponse:
    return RfiSummaryResponse.from_dto(
        await services.change_control.respond_rfi(
            session, actor_user_id=actor.user_id, rfi_id=rfi_id, data=body.to_dto()
        )
    )


@router.post("/rfis/{rfi_id}/transition", response_model=RfiSummaryResponse)
async def transition_rfi(
    rfi_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> RfiSummaryResponse:
    return RfiSummaryResponse.from_dto(
        await services.change_control.transition_rfi(
            session, actor_user_id=actor.user_id, rfi_id=rfi_id, target_status=body.target_status
        )
    )


@router.post(
    "/projects/{project_id}/ncrs", response_model=NcrResponse, status_code=status.HTTP_201_CREATED
)
async def create_ncr(
    project_id: UUID, body: NcrRequest, actor: Actor, session: Db, services: Services
) -> NcrResponse:
    return NcrResponse.from_dto(
        await services.change_control.create_ncr(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/ncrs/{ncr_id}/transition", response_model=NcrResponse)
async def transition_ncr(
    ncr_id: UUID, body: NcrTransitionRequest, actor: Actor, session: Db, services: Services
) -> NcrResponse:
    return NcrResponse.from_dto(
        await services.change_control.transition_ncr(
            session, actor_user_id=actor.user_id, ncr_id=ncr_id, data=body.to_dto()
        )
    )


@router.post(
    "/projects/{project_id}/discrepancy-cases",
    response_model=DiscrepancyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_discrepancy(
    project_id: UUID, body: DiscrepancyRequest, actor: Actor, session: Db, services: Services
) -> DiscrepancyResponse:
    return DiscrepancyResponse.from_dto(
        await services.change_control.create_discrepancy(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/discrepancy-cases/{case_id}/transition", response_model=DiscrepancyResponse)
async def transition_discrepancy(
    case_id: UUID, body: DiscrepancyTransitionRequest, actor: Actor, session: Db, services: Services
) -> DiscrepancyResponse:
    return DiscrepancyResponse.from_dto(
        await services.change_control.transition_discrepancy(
            session, actor_user_id=actor.user_id, case_id=case_id, data=body.to_dto()
        )
    )
