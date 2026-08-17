"""Published Phase 9 finance contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.finance.schemas import (
    ImportBatchCreate,
    ImportBatchSummary,
    ReconciliationCreate,
    ReconciliationReview,
    ReconciliationSummary,
    VoucherCreate,
    VoucherSummary,
)


class FinanceNotAuthorisedError(Exception):
    pass


class FinanceNotFoundError(Exception):
    pass


class FinanceConflictError(Exception):
    pass


class FinanceContract(Protocol):
    async def create_import_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ImportBatchCreate
    ) -> ImportBatchSummary: ...
    async def validate_import_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID
    ) -> ImportBatchSummary: ...
    async def import_voucher(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID, data: VoucherCreate
    ) -> VoucherSummary: ...
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
