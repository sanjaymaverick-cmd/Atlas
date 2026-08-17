"""Per-request dependencies for sessions, authentication, and services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from atlas.api.errors import UnauthenticatedError
from atlas.modules.change_control.contracts import ChangeControlContract
from atlas.modules.commercial.contracts import CommercialContract
from atlas.modules.compliance.contracts import ComplianceContract
from atlas.modules.construction.contracts import ConstructionContract
from atlas.modules.documents.contracts import DocumentsContract
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.identity.schemas import RelyingParty, SessionContext
from atlas.modules.land.contracts import LandContract
from atlas.modules.organization.contracts import OrganizationContract
from atlas.modules.project_controls.contracts import ProjectControlsContract
from atlas.platform.access_control import DEFAULT_MAX_SESSION_RISK


@dataclass(frozen=True, slots=True)
class ApiServices:
    session_factory: async_sessionmaker[AsyncSession]
    identity: IdentityContract
    organization: OrganizationContract
    documents: DocumentsContract
    land: LandContract
    compliance: ComplianceContract
    commercial: CommercialContract
    construction: ConstructionContract
    project_controls: ProjectControlsContract
    change_control: ChangeControlContract
    relying_party: RelyingParty


def get_services(request: Request) -> ApiServices:
    return cast(ApiServices, request.app.state.services)


async def get_session(
    services: Annotated[ApiServices, Depends(get_services)],
) -> AsyncIterator[AsyncSession]:
    async with services.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


bearer = HTTPBearer(auto_error=False)


async def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
    db_session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> SessionContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthenticatedError
    context = await services.identity.authenticate_session_token(
        db_session, credentials.credentials
    )
    if context is None:
        raise UnauthenticatedError
    if context.risk_score > DEFAULT_MAX_SESSION_RISK:
        raise UnauthenticatedError
    return context
