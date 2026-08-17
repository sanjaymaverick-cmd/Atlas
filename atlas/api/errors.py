"""Safe, consistent HTTP error responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from atlas.modules.commercial.contracts import (
    CommercialConflictError,
    CommercialNotAuthorisedError,
    CommercialNotFoundError,
)
from atlas.modules.compliance.contracts import (
    ComplianceConflictError,
    ComplianceNotAuthorisedError,
    ComplianceNotFoundError,
)
from atlas.modules.documents.contracts import (
    DocumentConflictError,
    DocumentNotAuthorisedError,
    DocumentNotFoundError,
)
from atlas.modules.land.contracts import (
    LandConflictError,
    LandNotAuthorisedError,
    LandNotFoundError,
)
from atlas.modules.organization.contracts import ConflictError, NotAuthorisedError, NotFoundError
from atlas.platform.step_up import StepUpRequiredError


class UnauthenticatedError(Exception):
    """Raised when no active opaque session matches the presented token."""


def error_body(code: str, message: str, *, details: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthenticatedError)
    async def unauthenticated_handler(request: Request, exc: UnauthenticatedError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_body("unauthenticated", "authentication is required"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(NotAuthorisedError)
    @app.exception_handler(DocumentNotAuthorisedError)
    @app.exception_handler(LandNotAuthorisedError)
    @app.exception_handler(ComplianceNotAuthorisedError)
    @app.exception_handler(CommercialNotAuthorisedError)
    async def forbidden_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_body("forbidden", "the session may not perform this action"),
        )

    @app.exception_handler(NotFoundError)
    @app.exception_handler(DocumentNotFoundError)
    @app.exception_handler(LandNotFoundError)
    @app.exception_handler(ComplianceNotFoundError)
    @app.exception_handler(CommercialNotFoundError)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content=error_body("not_found", str(exc)))

    @app.exception_handler(ConflictError)
    @app.exception_handler(DocumentConflictError)
    @app.exception_handler(LandConflictError)
    @app.exception_handler(ComplianceConflictError)
    @app.exception_handler(CommercialConflictError)
    async def conflict_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content=error_body("conflict", str(exc)))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "request validation failed", details=details),
        )

    @app.exception_handler(StepUpRequiredError)
    async def step_up_handler(request: Request, exc: StepUpRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_body("step_up_required", "fresh passkey verification is required"),
        )
