"""Published Phase 9 finance contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.finance.schemas import (
    ExternalVoucherCreate,
    ExternalVoucherSummary,
    LedgerSyncBatchCreate,
    LedgerSyncBatchSummary,
    ReconciliationCreate,
    ReconciliationReview,
    ReconciliationSummary,
)


class FinanceNotAuthorisedError(Exception):
    pass


class FinanceNotFoundError(Exception):
    pass


class FinanceConflictError(Exception):
    pass


class FinanceContract(Protocol):
    async def create_sync_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, data: LedgerSyncBatchCreate
    ) -> LedgerSyncBatchSummary: ...
    async def validate_sync_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID
    ) -> LedgerSyncBatchSummary: ...
    async def record_external_voucher(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID, data: ExternalVoucherCreate
    ) -> ExternalVoucherSummary: ...
    async def create_reconciliation(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ReconciliationCreate
    ) -> ReconciliationSummary: ...
    async def review_reconciliation(
        self,
        s: AsyncSession,
        *,
        actor_user_id: UUID,
        reconciliation_id: UUID,
        data: ReconciliationReview,
    ) -> ReconciliationSummary: ...
    async def list_sync_batches(
        self, s: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[LedgerSyncBatchSummary]: ...
    async def list_external_vouchers(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID
    ) -> list[ExternalVoucherSummary]: ...
    async def list_reconciliations(
        self, s: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[ReconciliationSummary]: ...
