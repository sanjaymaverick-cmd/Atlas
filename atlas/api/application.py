"""FastAPI application factory and production composition root."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from atlas.api.dependencies import ApiServices
from atlas.api.errors import error_body, install_error_handlers
from atlas.api.projects import router as projects_router
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.identity.service import IdentityService
from atlas.modules.organization.contracts import OrganizationContract
from atlas.modules.organization.service import OrganizationService
from atlas.platform.db import create_engine, create_session_factory


def create_app(
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    identity_service: IdentityContract | None = None,
    organization_service: OrganizationContract | None = None,
    dispose_engine: bool = False,
) -> FastAPI:
    identity = identity_service if identity_service is not None else IdentityService()
    organization = (
        organization_service if organization_service is not None else OrganizationService(identity)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if dispose_engine:
            await engine.dispose()

    app = FastAPI(title="Atlas API", version="0.1.0", lifespan=lifespan)
    app.state.services = ApiServices(
        session_factory=session_factory, identity=identity, organization=organization
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

    app.include_router(projects_router)
    return app


def create_default_app() -> FastAPI:
    """Build the production app from environment configuration."""
    try:
        database_url = os.environ["ATLAS_DATABASE_URL"]
    except KeyError as exc:
        raise RuntimeError("ATLAS_DATABASE_URL is required") from exc
    engine = create_engine(database_url)
    return create_app(
        engine=engine,
        session_factory=create_session_factory(engine),
        dispose_engine=True,
    )
