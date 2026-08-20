"""Published Compliance service contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.compliance.schemas import (
    ComplianceObligationCreate,
    ComplianceObligationSummary,
    ReraRegistrationCreate,
    ReraRegistrationSummary,
)


class ComplianceNotAuthorisedError(Exception):
    pass


class ComplianceNotFoundError(Exception):
    pass


class ComplianceConflictError(Exception):
    pass


class ComplianceContract(Protocol):
    async def create_registration(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ReraRegistrationCreate
    ) -> ReraRegistrationSummary: ...
    async def transition_registration(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        registration_id: UUID,
        target_status: str,
    ) -> ReraRegistrationSummary: ...
    async def create_obligation(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ComplianceObligationCreate
    ) -> ComplianceObligationSummary: ...
    async def transition_obligation(
        self, session: AsyncSession, *, actor_user_id: UUID, obligation_id: UUID, target_status: str
    ) -> ComplianceObligationSummary: ...
    async def list_registrations(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ReraRegistrationSummary]: ...
    async def list_obligations(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ComplianceObligationSummary]: ...
