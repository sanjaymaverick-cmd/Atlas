"""Thin HTTP adapter for the fail-closed assistant safety boundary."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.ai_assistant_schemas import AssistantRequestBody, AssistantResponse
from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.post("/queries", response_model=AssistantResponse)
async def ask(
    body: AssistantRequestBody, actor: Actor, session: Db, services: Services
) -> AssistantResponse:
    return AssistantResponse.from_dto(
        await services.assistant.ask(session, actor_user_id=actor.user_id, request=body.to_dto())
    )
