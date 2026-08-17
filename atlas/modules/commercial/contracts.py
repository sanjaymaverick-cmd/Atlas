"""Published Phase 4 commercial contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.commercial.schemas import (
    BudgetCreate,
    BudgetLineCreate,
    BudgetLineSummary,
    BudgetSummary,
    ContractCreate,
    ContractExecution,
    ContractSummary,
    InsuranceCreate,
    InsuranceSummary,
    KycRecordCreate,
    KycRecordSummary,
    LabourComplianceCreate,
    LabourComplianceSummary,
    MilestoneCreate,
    MilestoneSummary,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
    PurchaseOrderLineSummary,
    PurchaseOrderSummary,
    VendorOnboardingSummary,
)


class CommercialNotAuthorisedError(Exception):
    pass


class CommercialNotFoundError(Exception):
    pass


class CommercialConflictError(Exception):
    pass


class CommercialContract(Protocol):
    async def list_budgets(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[BudgetSummary]: ...
    async def create_budget(
        self, session: AsyncSession, *, actor_user_id: UUID, data: BudgetCreate
    ) -> BudgetSummary: ...
    async def add_budget_line(
        self, session: AsyncSession, *, actor_user_id: UUID, budget_id: UUID, data: BudgetLineCreate
    ) -> BudgetLineSummary: ...
    async def transition_budget(
        self, session: AsyncSession, *, actor_user_id: UUID, budget_id: UUID, target_status: str
    ) -> BudgetSummary: ...
    async def invite_vendor(
        self, session: AsyncSession, *, actor_user_id: UUID, vendor_id: UUID
    ) -> VendorOnboardingSummary: ...
    async def transition_vendor(
        self, session: AsyncSession, *, actor_user_id: UUID, onboarding_id: UUID, target_status: str
    ) -> VendorOnboardingSummary: ...
    async def add_kyc_record(
        self, session: AsyncSession, *, actor_user_id: UUID, data: KycRecordCreate
    ) -> KycRecordSummary: ...
    async def verify_kyc_record(
        self, session: AsyncSession, *, actor_user_id: UUID, record_id: UUID, approve: bool
    ) -> KycRecordSummary: ...
    async def create_purchase_order(
        self, session: AsyncSession, *, actor_user_id: UUID, data: PurchaseOrderCreate
    ) -> PurchaseOrderSummary: ...
    async def add_purchase_order_line(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        purchase_order_id: UUID,
        data: PurchaseOrderLineCreate,
    ) -> PurchaseOrderLineSummary: ...
    async def transition_purchase_order(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        purchase_order_id: UUID,
        target_status: str,
    ) -> PurchaseOrderSummary: ...
    async def create_contract(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ContractCreate
    ) -> ContractSummary: ...
    async def add_milestone(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        contract_id: UUID,
        data: MilestoneCreate,
    ) -> MilestoneSummary: ...
    async def transition_contract(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        contract_id: UUID,
        target_status: str,
        execution: ContractExecution | None = None,
    ) -> ContractSummary: ...
    async def create_insurance(
        self, session: AsyncSession, *, actor_user_id: UUID, data: InsuranceCreate
    ) -> InsuranceSummary: ...
    async def transition_insurance(
        self, session: AsyncSession, *, actor_user_id: UUID, policy_id: UUID, target_status: str
    ) -> InsuranceSummary: ...
    async def create_labour_compliance(
        self, session: AsyncSession, *, actor_user_id: UUID, data: LabourComplianceCreate
    ) -> LabourComplianceSummary: ...
    async def transition_labour_compliance(
        self, session: AsyncSession, *, actor_user_id: UUID, record_id: UUID, target_status: str
    ) -> LabourComplianceSummary: ...
