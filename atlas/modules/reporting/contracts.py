"""Published Phase 10 reporting contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.reporting.schemas import (
    EntityDashboard,
    ProjectDashboard,
    ReportRequestCreate,
    ReportRequestSummary,
)


class ReportingNotAuthorisedError(Exception):
    pass


class ReportingNotFoundError(Exception):
    pass


class ReportingConflictError(Exception):
    pass


class ReportingContract(Protocol):
    async def get_project_dashboard(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
    ) -> ProjectDashboard: ...
    async def get_entity_dashboard(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        legal_entity_id: UUID,
    ) -> EntityDashboard: ...
    async def create_report_request(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        data: ReportRequestCreate,
    ) -> ReportRequestSummary: ...
