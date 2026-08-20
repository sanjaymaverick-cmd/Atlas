"""Published Phase 6 service contract and refusal types."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.project_controls.schemas import (
    BimImportCreate,
    BimImportSummary,
    CostCodeCreate,
    CostCodeSummary,
    IssuanceCreate,
    IssuanceSummary,
    MaterialCreate,
    MaterialSummary,
    QuantityCreate,
    QuantitySummary,
    ReceiptCreate,
    ReceiptSummary,
)


class ProjectControlsNotAuthorisedError(Exception):
    pass


class ProjectControlsNotFoundError(Exception):
    pass


class ProjectControlsConflictError(Exception):
    pass


class ProjectControlsContract(Protocol):
    async def register_bim_import(
        self, session: AsyncSession, *, actor_user_id: UUID, data: BimImportCreate
    ) -> BimImportSummary: ...
    async def transition_bim_import(
        self, session: AsyncSession, *, actor_user_id: UUID, import_id: UUID, target_status: str
    ) -> BimImportSummary: ...
    async def create_cost_code(
        self, session: AsyncSession, *, actor_user_id: UUID, data: CostCodeCreate
    ) -> CostCodeSummary: ...
    async def create_quantity(
        self, session: AsyncSession, *, actor_user_id: UUID, data: QuantityCreate
    ) -> QuantitySummary: ...
    async def verify_quantity(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        quantity_id: UUID,
        verified_quantity: Decimal,
    ) -> QuantitySummary: ...
    async def approve_quantity(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        quantity_id: UUID,
        final_quantity: Decimal,
    ) -> QuantitySummary: ...
    async def create_material(
        self, session: AsyncSession, *, actor_user_id: UUID, data: MaterialCreate
    ) -> MaterialSummary: ...
    async def record_receipt(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ReceiptCreate
    ) -> ReceiptSummary: ...
    async def issue_material(
        self, session: AsyncSession, *, actor_user_id: UUID, receipt_id: UUID, data: IssuanceCreate
    ) -> IssuanceSummary: ...
    async def list_bim_imports(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[BimImportSummary]: ...
    async def list_cost_codes(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[CostCodeSummary]: ...
    async def list_quantities(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[QuantitySummary]: ...
    async def list_receipts(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ReceiptSummary]: ...
    async def list_materials(
        self, s: AsyncSession, *, actor_user_id: UUID
    ) -> list[MaterialSummary]: ...
