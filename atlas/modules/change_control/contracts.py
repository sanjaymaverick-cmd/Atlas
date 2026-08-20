"""Published Phase 7 contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.change_control.schemas import (
    ChangeCreate,
    ChangeSummary,
    DiscrepancyCreate,
    DiscrepancySummary,
    DiscrepancyTransition,
    NcrCreate,
    NcrSummary,
    NcrTransition,
    RfiCreate,
    RfiResponse,
    RfiSummary,
)


class ChangeControlNotAuthorisedError(Exception):
    pass


class ChangeControlNotFoundError(Exception):
    pass


class ChangeControlConflictError(Exception):
    pass


class ChangeControlContract(Protocol):
    async def create_change(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ChangeCreate
    ) -> ChangeSummary: ...
    async def transition_change(
        self, s: AsyncSession, *, actor_user_id: UUID, change_id: UUID, target_status: str
    ) -> ChangeSummary: ...
    async def create_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, data: RfiCreate
    ) -> RfiSummary: ...
    async def respond_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, rfi_id: UUID, data: RfiResponse
    ) -> RfiSummary: ...
    async def transition_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, rfi_id: UUID, target_status: str
    ) -> RfiSummary: ...
    async def create_ncr(
        self, s: AsyncSession, *, actor_user_id: UUID, data: NcrCreate
    ) -> NcrSummary: ...
    async def transition_ncr(
        self, s: AsyncSession, *, actor_user_id: UUID, ncr_id: UUID, data: NcrTransition
    ) -> NcrSummary: ...
    async def create_discrepancy(
        self, s: AsyncSession, *, actor_user_id: UUID, data: DiscrepancyCreate
    ) -> DiscrepancySummary: ...
    async def transition_discrepancy(
        self, s: AsyncSession, *, actor_user_id: UUID, case_id: UUID, data: DiscrepancyTransition
    ) -> DiscrepancySummary: ...
    async def list_changes(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ChangeSummary]: ...
    async def list_rfis(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[RfiSummary]: ...
    async def list_ncrs(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[NcrSummary]: ...
    async def list_discrepancies(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[DiscrepancySummary]: ...
