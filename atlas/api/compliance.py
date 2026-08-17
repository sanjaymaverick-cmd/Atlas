"""Thin HTTP adapters for Phase 3 statutory compliance operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.schemas import (
    ComplianceObligationCreateRequest,
    ComplianceObligationResponse,
    LifecycleTransitionRequest,
    ReraRegistrationCreateRequest,
    ReraRegistrationResponse,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["compliance"])


@router.post(
    "/projects/{project_id}/rera-registrations",
    response_model=ReraRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_registration(
    project_id: UUID,
    body: ReraRegistrationCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ReraRegistrationResponse:
    value = await services.compliance.create_registration(
        session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
    )
    return ReraRegistrationResponse.from_dto(value)


@router.post(
    "/rera-registrations/{registration_id}/transition", response_model=ReraRegistrationResponse
)
async def transition_registration(
    registration_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ReraRegistrationResponse:
    value = await services.compliance.transition_registration(
        session,
        actor_user_id=actor.user_id,
        registration_id=registration_id,
        target_status=body.target_status,
    )
    return ReraRegistrationResponse.from_dto(value)


@router.post(
    "/compliance-obligations",
    response_model=ComplianceObligationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_obligation(
    body: ComplianceObligationCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ComplianceObligationResponse:
    value = await services.compliance.create_obligation(
        session, actor_user_id=actor.user_id, data=body.to_dto()
    )
    return ComplianceObligationResponse.from_dto(value)


@router.post(
    "/compliance-obligations/{obligation_id}/transition",
    response_model=ComplianceObligationResponse,
)
async def transition_obligation(
    obligation_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ComplianceObligationResponse:
    value = await services.compliance.transition_obligation(
        session,
        actor_user_id=actor.user_id,
        obligation_id=obligation_id,
        target_status=body.target_status,
    )
    return ComplianceObligationResponse.from_dto(value)
