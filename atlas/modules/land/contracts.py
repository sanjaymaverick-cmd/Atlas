"""Published Land service contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.land.schemas import (
    DueDiligenceCreate,
    DueDiligenceSummary,
    InstallmentCreate,
    InstallmentSummary,
    LandParcelCreate,
    LandParcelSummary,
    LegalApprovalCreate,
    LegalApprovalSummary,
    LoanCreate,
    LoanSummary,
)


class LandNotAuthorisedError(Exception):
    pass


class LandNotFoundError(Exception):
    pass


class LandConflictError(Exception):
    pass


class LandContract(Protocol):
    async def create_parcel(
        self, session: AsyncSession, *, actor_user_id: UUID, data: LandParcelCreate
    ) -> LandParcelSummary: ...

    async def list_parcels(
        self, session: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[LandParcelSummary]: ...

    async def transition_parcel(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        target_status: str,
    ) -> LandParcelSummary: ...

    async def add_due_diligence(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        data: DueDiligenceCreate,
    ) -> DueDiligenceSummary: ...

    async def resolve_due_diligence(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        item_id: UUID,
        result: str,
        notes: str | None,
    ) -> DueDiligenceSummary: ...

    async def add_legal_approval(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        data: LegalApprovalCreate,
    ) -> LegalApprovalSummary: ...

    async def transition_legal_approval(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        approval_id: UUID,
        target_status: str,
    ) -> LegalApprovalSummary: ...

    async def create_loan(
        self, session: AsyncSession, *, actor_user_id: UUID, data: LoanCreate
    ) -> LoanSummary: ...

    async def add_installment(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        loan_id: UUID,
        data: InstallmentCreate,
    ) -> InstallmentSummary: ...

    async def transition_installment(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        installment_id: UUID,
        target_status: str,
    ) -> InstallmentSummary: ...

    async def transition_loan(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        loan_id: UUID,
        target_status: str,
    ) -> LoanSummary: ...
