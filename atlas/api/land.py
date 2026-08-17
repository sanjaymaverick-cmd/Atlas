"""Thin HTTP adapters for Phase 3 land and financing operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.schemas import (
    DueDiligenceCreateRequest,
    DueDiligenceResolveRequest,
    DueDiligenceResponse,
    InstallmentCreateRequest,
    InstallmentResponse,
    LandParcelCreateRequest,
    LandParcelResponse,
    LegalApprovalCreateRequest,
    LegalApprovalResponse,
    LifecycleTransitionRequest,
    LoanCreateRequest,
    LoanResponse,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["land"])


@router.get(
    "/legal-entities/{legal_entity_id}/land-parcels", response_model=list[LandParcelResponse]
)
async def list_parcels(
    legal_entity_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[LandParcelResponse]:
    values = await services.land.list_parcels(
        session, actor_user_id=actor.user_id, legal_entity_id=legal_entity_id
    )
    return [LandParcelResponse.from_dto(value) for value in values]


@router.post(
    "/legal-entities/{legal_entity_id}/land-parcels",
    response_model=LandParcelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_parcel(
    legal_entity_id: UUID,
    body: LandParcelCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LandParcelResponse:
    value = await services.land.create_parcel(
        session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
    )
    return LandParcelResponse.from_dto(value)


@router.post("/land-parcels/{parcel_id}/transition", response_model=LandParcelResponse)
async def transition_parcel(
    parcel_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LandParcelResponse:
    value = await services.land.transition_parcel(
        session, actor_user_id=actor.user_id, parcel_id=parcel_id, target_status=body.target_status
    )
    return LandParcelResponse.from_dto(value)


@router.post(
    "/land-parcels/{parcel_id}/due-diligence",
    response_model=DueDiligenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_due_diligence(
    parcel_id: UUID,
    body: DueDiligenceCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> DueDiligenceResponse:
    value = await services.land.add_due_diligence(
        session, actor_user_id=actor.user_id, parcel_id=parcel_id, data=body.to_dto()
    )
    return DueDiligenceResponse.from_dto(value)


@router.post("/due-diligence/{item_id}/resolve", response_model=DueDiligenceResponse)
async def resolve_due_diligence(
    item_id: UUID,
    body: DueDiligenceResolveRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> DueDiligenceResponse:
    value = await services.land.resolve_due_diligence(
        session, actor_user_id=actor.user_id, item_id=item_id, result=body.result, notes=body.notes
    )
    return DueDiligenceResponse.from_dto(value)


@router.post(
    "/land-parcels/{parcel_id}/legal-approvals",
    response_model=LegalApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_legal_approval(
    parcel_id: UUID,
    body: LegalApprovalCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LegalApprovalResponse:
    value = await services.land.add_legal_approval(
        session, actor_user_id=actor.user_id, parcel_id=parcel_id, data=body.to_dto()
    )
    return LegalApprovalResponse.from_dto(value)


@router.post("/land-legal-approvals/{approval_id}/transition", response_model=LegalApprovalResponse)
async def transition_legal_approval(
    approval_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LegalApprovalResponse:
    value = await services.land.transition_legal_approval(
        session,
        actor_user_id=actor.user_id,
        approval_id=approval_id,
        target_status=body.target_status,
    )
    return LegalApprovalResponse.from_dto(value)


@router.post(
    "/legal-entities/{legal_entity_id}/loans",
    response_model=LoanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_loan(
    legal_entity_id: UUID,
    body: LoanCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LoanResponse:
    value = await services.land.create_loan(
        session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
    )
    return LoanResponse.from_dto(value)


@router.post("/loans/{loan_id}/transition", response_model=LoanResponse)
async def transition_loan(
    loan_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> LoanResponse:
    value = await services.land.transition_loan(
        session, actor_user_id=actor.user_id, loan_id=loan_id, target_status=body.target_status
    )
    return LoanResponse.from_dto(value)


@router.post(
    "/loans/{loan_id}/installments",
    response_model=InstallmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_installment(
    loan_id: UUID,
    body: InstallmentCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> InstallmentResponse:
    value = await services.land.add_installment(
        session, actor_user_id=actor.user_id, loan_id=loan_id, data=body.to_dto()
    )
    return InstallmentResponse.from_dto(value)


@router.post("/loan-installments/{installment_id}/transition", response_model=InstallmentResponse)
async def transition_installment(
    installment_id: UUID,
    body: LifecycleTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> InstallmentResponse:
    value = await services.land.transition_installment(
        session,
        actor_user_id=actor.user_id,
        installment_id=installment_id,
        target_status=body.target_status,
    )
    return InstallmentResponse.from_dto(value)
