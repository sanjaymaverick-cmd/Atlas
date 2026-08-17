"""Thin HTTP adapters for Phase 9 finance reconciliation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.finance_schemas import (
    ImportBatchRequest,
    ImportBatchResponse,
    ReconciliationRequest,
    ReconciliationResponse,
    ReviewRequest,
    VoucherRequest,
    VoucherResponse,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["finance"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post(
    "/legal-entities/{legal_entity_id}/tally-imports",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_import(
    legal_entity_id: UUID, body: ImportBatchRequest, actor: Actor, session: Db, services: Services
) -> ImportBatchResponse:
    return ImportBatchResponse.from_dto(
        await services.finance.create_import_batch(
            session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
        )
    )


@router.post("/tally-imports/{batch_id}/validate", response_model=ImportBatchResponse)
async def validate_import(
    batch_id: UUID, actor: Actor, session: Db, services: Services
) -> ImportBatchResponse:
    return ImportBatchResponse.from_dto(
        await services.finance.validate_import_batch(
            session, actor_user_id=actor.user_id, batch_id=batch_id
        )
    )


@router.post(
    "/tally-imports/{batch_id}/vouchers",
    response_model=VoucherResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_voucher(
    batch_id: UUID, body: VoucherRequest, actor: Actor, session: Db, services: Services
) -> VoucherResponse:
    return VoucherResponse.from_dto(
        await services.finance.import_voucher(
            session, actor_user_id=actor.user_id, batch_id=batch_id, data=body.to_dto()
        )
    )


@router.post(
    "/legal-entities/{legal_entity_id}/reconciliations",
    response_model=ReconciliationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reconciliation(
    legal_entity_id: UUID,
    body: ReconciliationRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> ReconciliationResponse:
    return ReconciliationResponse.from_dto(
        await services.finance.create_reconciliation(
            session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
        )
    )


@router.post("/reconciliations/{reconciliation_id}/review", response_model=ReconciliationResponse)
async def review_reconciliation(
    reconciliation_id: UUID, body: ReviewRequest, actor: Actor, session: Db, services: Services
) -> ReconciliationResponse:
    return ReconciliationResponse.from_dto(
        await services.finance.review_reconciliation(
            session,
            actor_user_id=actor.user_id,
            reconciliation_id=reconciliation_id,
            data=body.to_dto(),
        )
    )
