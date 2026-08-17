"""Thin HTTP adapters for Phase 8 customer lifecycle."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.customer_lifecycle_schemas import (
    BookingContractResponse,
    BookingRequest,
    BookingResponse,
    CollectionRequest,
    CollectionResponse,
    ContractLinkRequest,
    InstallmentRequest,
    InstallmentResponse,
    PlanRequest,
    PlanResponse,
    PossessionRequest,
    PossessionResponse,
    RegistrationRequest,
    RegistrationResponse,
)
from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["customer-lifecycle"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post(
    "/projects/{project_id}/bookings",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    project_id: UUID, body: BookingRequest, actor: Actor, session: Db, services: Services
) -> BookingResponse:
    return BookingResponse.from_dto(
        await services.customer_lifecycle.create_booking(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: UUID, actor: Actor, session: Db, services: Services
) -> BookingResponse:
    return BookingResponse.from_dto(
        await services.customer_lifecycle.cancel_booking(
            session, actor_user_id=actor.user_id, booking_id=booking_id
        )
    )


@router.post(
    "/bookings/{booking_id}/payment-plans",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    booking_id: UUID, body: PlanRequest, actor: Actor, session: Db, services: Services
) -> PlanResponse:
    return PlanResponse.from_dto(
        await services.customer_lifecycle.create_plan(
            session, actor_user_id=actor.user_id, booking_id=booking_id, data=body.to_dto()
        )
    )


@router.post(
    "/payment-plans/{plan_id}/installments",
    response_model=InstallmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_installment(
    plan_id: UUID, body: InstallmentRequest, actor: Actor, session: Db, services: Services
) -> InstallmentResponse:
    return InstallmentResponse.from_dto(
        await services.customer_lifecycle.add_installment(
            session, actor_user_id=actor.user_id, plan_id=plan_id, data=body.to_dto()
        )
    )


@router.post(
    "/bookings/{booking_id}/collections",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_collection(
    booking_id: UUID, body: CollectionRequest, actor: Actor, session: Db, services: Services
) -> CollectionResponse:
    return CollectionResponse.from_dto(
        await services.customer_lifecycle.record_collection(
            session, actor_user_id=actor.user_id, booking_id=booking_id, data=body.to_dto()
        )
    )


@router.post("/collections/{collection_id}/allocate", response_model=CollectionResponse)
async def allocate_collection(
    collection_id: UUID, actor: Actor, session: Db, services: Services
) -> CollectionResponse:
    return CollectionResponse.from_dto(
        await services.customer_lifecycle.allocate_collection(
            session, actor_user_id=actor.user_id, collection_id=collection_id
        )
    )


@router.post("/bookings/{booking_id}/registration", response_model=RegistrationResponse)
async def transition_registration(
    booking_id: UUID, body: RegistrationRequest, actor: Actor, session: Db, services: Services
) -> RegistrationResponse:
    return RegistrationResponse.from_dto(
        await services.customer_lifecycle.transition_registration(
            session, actor_user_id=actor.user_id, booking_id=booking_id, data=body.to_dto()
        )
    )


@router.post("/bookings/{booking_id}/possession", response_model=PossessionResponse)
async def transition_possession(
    booking_id: UUID, body: PossessionRequest, actor: Actor, session: Db, services: Services
) -> PossessionResponse:
    return PossessionResponse.from_dto(
        await services.customer_lifecycle.transition_possession(
            session, actor_user_id=actor.user_id, booking_id=booking_id, data=body.to_dto()
        )
    )


@router.post(
    "/bookings/{booking_id}/executed-contract",
    response_model=BookingContractResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_contract(
    booking_id: UUID, body: ContractLinkRequest, actor: Actor, session: Db, services: Services
) -> BookingContractResponse:
    return BookingContractResponse.from_dto(
        await services.customer_lifecycle.link_executed_contract(
            session,
            actor_user_id=actor.user_id,
            booking_id=booking_id,
            contract_id=body.contract_id,
        )
    )
