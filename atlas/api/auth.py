"""Thin HTTP adapter for WebAuthn registration and authentication."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_services, get_session
from atlas.api.errors import error_body
from atlas.modules.identity.contracts import InvalidCeremonyError, WebAuthnError

router = APIRouter(prefix="/api/v1/auth/webauthn", tags=["authentication"])


class RegistrationOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


class CeremonyResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ceremony_id: UUID
    credential: dict[str, Any]
    device_name: str | None = Field(default=None, max_length=200)


class AuthenticationResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ceremony_id: UUID
    credential: dict[str, Any]


@router.post("/registration/options")
async def registration_options(
    body: RegistrationOptionsRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict[str, Any]:
    options = await services.identity.begin_registration(
        session, user_id=body.user_id, rp=services.relying_party
    )
    return {"ceremony_id": options.ceremony_id, "public_key": options.public_key}


@router.post("/registration/verify", response_model=None)
async def registration_verify(
    body: CeremonyResponseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict[str, Any] | JSONResponse:
    try:
        device_id = await services.identity.complete_registration(
            session,
            ceremony_id=body.ceremony_id,
            credential=body.credential,
            device_name=body.device_name,
            rp=services.relying_party,
        )
    except (InvalidCeremonyError, WebAuthnError):
        return JSONResponse(
            status_code=400,
            content=error_body("invalid_ceremony", "registration could not be verified"),
        )
    return {"device_id": device_id, "status": "pending_approval"}


@router.post("/authentication/options")
async def authentication_options(
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict[str, Any]:
    options = await services.identity.begin_authentication(session, rp=services.relying_party)
    return {"ceremony_id": options.ceremony_id, "public_key": options.public_key}


@router.post("/authentication/verify", response_model=None)
async def authentication_verify(
    body: AuthenticationResponseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> dict[str, Any] | JSONResponse:
    try:
        outcome = await services.identity.complete_authentication(
            session,
            ceremony_id=body.ceremony_id,
            credential=body.credential,
            rp=services.relying_party,
        )
    except (InvalidCeremonyError, WebAuthnError):
        return JSONResponse(
            status_code=401,
            content=error_body("authentication_failed", "authentication failed"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    if outcome.clone_detected:
        return JSONResponse(
            status_code=401,
            content=error_body("authentication_failed", "authentication failed"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "session_token": outcome.session_token,
        "token_type": "bearer",
        "expires_at": outcome.expires_at,
    }
