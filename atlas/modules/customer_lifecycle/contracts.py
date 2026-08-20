"""Published Phase 8 contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.customer_lifecycle.schemas import (
    BookingContractSummary,
    BookingCreate,
    BookingSummary,
    CollectionCreate,
    CollectionSummary,
    InstallmentCreate,
    InstallmentSummary,
    PlanCreate,
    PlanSummary,
    PossessionSummary,
    PossessionTransition,
    RegistrationSummary,
    RegistrationTransition,
)


class CustomerLifecycleNotAuthorisedError(Exception):
    pass


class CustomerLifecycleNotFoundError(Exception):
    pass


class CustomerLifecycleConflictError(Exception):
    pass


class CustomerLifecycleContract(Protocol):
    async def create_booking(
        self, s: AsyncSession, *, actor_user_id: UUID, data: BookingCreate
    ) -> BookingSummary: ...
    async def cancel_booking(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID
    ) -> BookingSummary: ...
    async def create_plan(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: PlanCreate
    ) -> PlanSummary: ...
    async def add_installment(
        self, s: AsyncSession, *, actor_user_id: UUID, plan_id: UUID, data: InstallmentCreate
    ) -> InstallmentSummary: ...
    async def record_collection(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: CollectionCreate
    ) -> CollectionSummary: ...
    async def allocate_collection(
        self, s: AsyncSession, *, actor_user_id: UUID, collection_id: UUID
    ) -> CollectionSummary: ...
    async def transition_registration(
        self,
        s: AsyncSession,
        *,
        actor_user_id: UUID,
        booking_id: UUID,
        data: RegistrationTransition,
    ) -> RegistrationSummary: ...
    async def transition_possession(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: PossessionTransition
    ) -> PossessionSummary: ...
    async def link_executed_contract(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, contract_id: UUID
    ) -> BookingContractSummary: ...
    async def list_bookings(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[BookingSummary]: ...
    async def list_payment_plans(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID
    ) -> list[PlanSummary]: ...
    async def list_collections(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID
    ) -> list[CollectionSummary]: ...
