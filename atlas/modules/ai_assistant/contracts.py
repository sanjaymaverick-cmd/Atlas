"""Published Phase 11 assistant contract and refusal types."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.ai_assistant.schemas import AssistantOutcome, AssistantRequest


class AssistantNotAuthorisedError(Exception):
    pass


class AssistantConflictError(Exception):
    pass


class AssistantContract(Protocol):
    async def ask(
        self, s: AsyncSession, *, actor_user_id: UUID, request: AssistantRequest
    ) -> AssistantOutcome: ...
