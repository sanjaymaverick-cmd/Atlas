"""FastAPI application factory and production composition root."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from atlas.api.auth import router as auth_router
from atlas.api.compliance import router as compliance_router
from atlas.api.dependencies import ApiServices
from atlas.api.documents import router as documents_router
from atlas.api.errors import error_body, install_error_handlers
from atlas.api.land import router as land_router
from atlas.api.projects import router as projects_router
from atlas.modules.compliance.contracts import ComplianceContract
from atlas.modules.compliance.service import ComplianceService
from atlas.modules.documents.contracts import DocumentsContract
from atlas.modules.documents.service import DocumentsService
from atlas.modules.documents.storage import DocumentStorage, LocalDocumentStorage
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.identity.schemas import RelyingParty
from atlas.modules.identity.service import IdentityService
from atlas.modules.land.contracts import LandContract
from atlas.modules.land.service import LandService
from atlas.modules.organization.contracts import OrganizationContract
from atlas.modules.organization.service import OrganizationService
from atlas.platform.db import create_engine, create_session_factory


def create_app(
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    identity_service: IdentityContract | None = None,
    organization_service: OrganizationContract | None = None,
    documents_service: DocumentsContract | None = None,
    land_service: LandContract | None = None,
    compliance_service: ComplianceContract | None = None,
    document_storage: DocumentStorage | None = None,
    relying_party: RelyingParty,
    dispose_engine: bool = False,
) -> FastAPI:
    identity = identity_service if identity_service is not None else IdentityService()
    organization = (
        organization_service if organization_service is not None else OrganizationService(identity)
    )
    documents = (
        documents_service
        if documents_service is not None
        else DocumentsService(identity, document_storage)
    )
    land = land_service if land_service is not None else LandService(identity)
    compliance = (
        compliance_service if compliance_service is not None else ComplianceService(identity)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if dispose_engine:
            await engine.dispose()

    app = FastAPI(title="Atlas API", version="0.1.0", lifespan=lifespan)
    app.state.services = ApiServices(
        session_factory=session_factory,
        identity=identity,
        organization=organization,
        documents=documents,
        land=land,
        compliance=compliance,
        relying_party=relying_party,
    )
    install_error_handlers(app)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"], response_model=None)
    async def ready() -> dict[str, str] | JSONResponse:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content=error_body("not_ready", "database connectivity check failed"),
            )
        return {"status": "ready"}

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(documents_router)
    app.include_router(land_router)
    app.include_router(compliance_router)
    return app


def create_default_app() -> FastAPI:
    """Build the production app from environment configuration."""
    try:
        database_url = os.environ["ATLAS_DATABASE_URL"]
    except KeyError as exc:
        raise RuntimeError("ATLAS_DATABASE_URL is required") from exc
    engine = create_engine(database_url)
    try:
        relying_party = RelyingParty(
            rp_id=os.environ["ATLAS_WEBAUTHN_RP_ID"],
            rp_name=os.environ.get("ATLAS_WEBAUTHN_RP_NAME", "Atlas"),
            origin=os.environ["ATLAS_WEBAUTHN_ORIGIN"],
        )
    except KeyError as exc:
        raise RuntimeError("ATLAS_WEBAUTHN_RP_ID and ATLAS_WEBAUTHN_ORIGIN are required") from exc
    try:
        document_storage_root = Path(os.environ["ATLAS_DOCUMENT_STORAGE_ROOT"])
    except KeyError as exc:
        raise RuntimeError("ATLAS_DOCUMENT_STORAGE_ROOT is required") from exc
    return create_app(
        engine=engine,
        session_factory=create_session_factory(engine),
        relying_party=relying_party,
        document_storage=LocalDocumentStorage(document_storage_root),
        dispose_engine=True,
    )
