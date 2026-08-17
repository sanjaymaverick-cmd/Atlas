"""Thin HTTP adapters for Phase 6 project controls."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.project_controls_schemas import (
    BimImportRequest,
    BimImportResponse,
    CostCodeRequest,
    CostCodeResponse,
    IssuanceRequest,
    IssuanceResponse,
    MaterialRequest,
    MaterialResponse,
    QuantityRequest,
    QuantityResponse,
    ReceiptRequest,
    ReceiptResponse,
    TransitionRequest,
    ValueRequest,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["project-controls"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post(
    "/projects/{project_id}/bim-imports",
    response_model=BimImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_bim(
    project_id: UUID, body: BimImportRequest, actor: Actor, session: Db, services: Services
) -> BimImportResponse:
    return BimImportResponse.from_dto(
        await services.project_controls.register_bim_import(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/bim-imports/{import_id}/transition", response_model=BimImportResponse)
async def transition_bim(
    import_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BimImportResponse:
    return BimImportResponse.from_dto(
        await services.project_controls.transition_bim_import(
            session,
            actor_user_id=actor.user_id,
            import_id=import_id,
            target_status=body.target_status,
        )
    )


@router.post(
    "/projects/{project_id}/cost-codes",
    response_model=CostCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cost_code(
    project_id: UUID, body: CostCodeRequest, actor: Actor, session: Db, services: Services
) -> CostCodeResponse:
    return CostCodeResponse.from_dto(
        await services.project_controls.create_cost_code(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post(
    "/projects/{project_id}/quantity-items",
    response_model=QuantityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quantity(
    project_id: UUID, body: QuantityRequest, actor: Actor, session: Db, services: Services
) -> QuantityResponse:
    return QuantityResponse.from_dto(
        await services.project_controls.create_quantity(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post("/quantity-items/{quantity_id}/verify", response_model=QuantityResponse)
async def verify_quantity(
    quantity_id: UUID, body: ValueRequest, actor: Actor, session: Db, services: Services
) -> QuantityResponse:
    return QuantityResponse.from_dto(
        await services.project_controls.verify_quantity(
            session,
            actor_user_id=actor.user_id,
            quantity_id=quantity_id,
            verified_quantity=body.quantity,
        )
    )


@router.post("/quantity-items/{quantity_id}/approve", response_model=QuantityResponse)
async def approve_quantity(
    quantity_id: UUID, body: ValueRequest, actor: Actor, session: Db, services: Services
) -> QuantityResponse:
    return QuantityResponse.from_dto(
        await services.project_controls.approve_quantity(
            session,
            actor_user_id=actor.user_id,
            quantity_id=quantity_id,
            final_quantity=body.quantity,
        )
    )


@router.post("/materials", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def create_material(
    body: MaterialRequest, actor: Actor, session: Db, services: Services
) -> MaterialResponse:
    return MaterialResponse.from_dto(
        await services.project_controls.create_material(
            session, actor_user_id=actor.user_id, data=body.to_dto()
        )
    )


@router.post(
    "/projects/{project_id}/material-receipts",
    response_model=ReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_receipt(
    project_id: UUID, body: ReceiptRequest, actor: Actor, session: Db, services: Services
) -> ReceiptResponse:
    return ReceiptResponse.from_dto(
        await services.project_controls.record_receipt(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post(
    "/material-receipts/{receipt_id}/issuances",
    response_model=IssuanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_material(
    receipt_id: UUID, body: IssuanceRequest, actor: Actor, session: Db, services: Services
) -> IssuanceResponse:
    return IssuanceResponse.from_dto(
        await services.project_controls.issue_material(
            session, actor_user_id=actor.user_id, receipt_id=receipt_id, data=body.to_dto()
        )
    )
