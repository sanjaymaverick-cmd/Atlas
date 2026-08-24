"""Thin HTTP adapters for Phase 9 finance reconciliation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.finance_schemas import (
    ExternalVoucherRequest,
    ExternalVoucherResponse,
    LedgerSyncBatchRequest,
    LedgerSyncBatchResponse,
    ReconciliationRequest,
    ReconciliationResponse,
    ReviewRequest,
)
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["finance"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post(
    "/legal-entities/{legal_entity_id}/ledger-sync-batches",
    response_model=LedgerSyncBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sync_batch(
    legal_entity_id: UUID,
    body: LedgerSyncBatchRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> LedgerSyncBatchResponse:
    return LedgerSyncBatchResponse.from_dto(
        await services.finance.create_sync_batch(
            session, actor_user_id=actor.user_id, data=body.to_dto(legal_entity_id)
        )
    )


@router.post("/ledger-sync-batches/{batch_id}/validate", response_model=LedgerSyncBatchResponse)
async def validate_sync_batch(
    batch_id: UUID, actor: Actor, session: Db, services: Services
) -> LedgerSyncBatchResponse:
    return LedgerSyncBatchResponse.from_dto(
        await services.finance.validate_sync_batch(
            session, actor_user_id=actor.user_id, batch_id=batch_id
        )
    )


@router.post(
    "/ledger-sync-batches/{batch_id}/vouchers",
    response_model=ExternalVoucherResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_external_voucher(
    batch_id: UUID, body: ExternalVoucherRequest, actor: Actor, session: Db, services: Services
) -> ExternalVoucherResponse:
    return ExternalVoucherResponse.from_dto(
        await services.finance.record_external_voucher(
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


# -- reads ------------------------------------------------------------------
# Added 2026-08-20; this router previously exposed writes only.


@router.get(
    "/legal-entities/{legal_entity_id}/ledger-sync-batches",
    response_model=list[LedgerSyncBatchResponse],
)
async def list_sync_batches(
    legal_entity_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[LedgerSyncBatchResponse]:
    rows = await services.finance.list_sync_batches(
        session, actor_user_id=actor.user_id, legal_entity_id=legal_entity_id
    )
    return [LedgerSyncBatchResponse.from_dto(row) for row in rows]


@router.get(
    "/ledger-sync-batches/{batch_id}/vouchers", response_model=list[ExternalVoucherResponse]
)
async def list_external_vouchers(
    batch_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[ExternalVoucherResponse]:
    rows = await services.finance.list_external_vouchers(
        session, actor_user_id=actor.user_id, batch_id=batch_id
    )
    return [ExternalVoucherResponse.from_dto(row) for row in rows]


@router.get(
    "/legal-entities/{legal_entity_id}/reconciliations",
    response_model=list[ReconciliationResponse],
)
async def list_reconciliations(
    legal_entity_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[ReconciliationResponse]:
    rows = await services.finance.list_reconciliations(
        session, actor_user_id=actor.user_id, legal_entity_id=legal_entity_id
    )
    return [ReconciliationResponse.from_dto(row) for row in rows]
