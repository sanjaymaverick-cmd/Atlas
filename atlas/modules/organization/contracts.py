"""Organization's published service contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.organization.schemas import ProjectCreate, ProjectSummary, ProjectUpdate


class NotAuthorisedError(Exception):
    """Raised when the caller's roles do not reach the requested scope."""


class NotFoundError(Exception):
    """Raised when the named entity or project does not exist."""


class ConflictError(Exception):
    """Raised when a write conflicts with an existing business record."""


class OrganizationContract(Protocol):
    """Operations the HTTP adapter and other composition roots may call."""

    async def get_project(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> ProjectSummary: ...

    async def list_projects(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        legal_entity_id: UUID,
    ) -> list[ProjectSummary]: ...

    async def create_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        data: ProjectCreate,
    ) -> ProjectSummary: ...

    async def update_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
        data: ProjectUpdate,
    ) -> ProjectSummary: ...

    async def archive_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
    ) -> ProjectSummary: ...
