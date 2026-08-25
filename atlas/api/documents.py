"""Thin HTTP adapter for Phase 2 document registry operations."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.api.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    ExportDecisionRequest,
    ExportRequestCreateRequest,
    ExportRequestResponse,
    PreviewGrantResponse,
    RevisionCreateRequest,
    RevisionResponse,
    RevisionTransitionRequest,
    ScanResultRequest,
)
from atlas.modules.identity.schemas import SessionContext
from atlas.platform.step_up import SensitiveAction, assert_step_up

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> DocumentResponse:
    value = await services.documents.get_document(
        session, actor_user_id=actor.user_id, document_id=document_id
    )
    return DocumentResponse.from_dto(value)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    project_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[DocumentResponse]:
    values = await services.documents.list_documents(
        session, actor_user_id=actor.user_id, project_id=project_id
    )
    return [DocumentResponse.from_dto(value) for value in values]


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    project_id: UUID,
    body: DocumentCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> DocumentResponse:
    value = await services.documents.create_document(
        session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
    )
    return DocumentResponse.from_dto(value)


@router.get("/documents/{document_id}/revisions", response_model=list[RevisionResponse])
async def list_revisions(
    document_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> list[RevisionResponse]:
    values = await services.documents.list_revisions(
        session, actor_user_id=actor.user_id, document_id=document_id
    )
    return [RevisionResponse.from_dto(value) for value in values]


@router.post(
    "/documents/{document_id}/revisions",
    response_model=RevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_revision(
    document_id: UUID,
    body: RevisionCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> RevisionResponse:
    value = await services.documents.add_revision(
        session,
        actor_user_id=actor.user_id,
        document_id=document_id,
        data=body.to_dto(),
    )
    return RevisionResponse.from_dto(value)


@router.post(
    "/documents/{document_id}/revision-content",
    response_model=RevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_revision_content(
    document_id: UUID,
    content: Annotated[bytes, Body(media_type="application/pdf")],
    revision_code: Annotated[str, Query(min_length=1, max_length=100)],
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
    issue_purpose: Annotated[str | None, Query(max_length=200)] = None,
    issue_date: Annotated[date | None, Query()] = None,
) -> RevisionResponse:
    value = await services.documents.add_revision_content(
        session,
        actor_user_id=actor.user_id,
        document_id=document_id,
        revision_code=revision_code,
        content=content,
        issue_purpose=issue_purpose,
        issue_date=issue_date,
    )
    return RevisionResponse.from_dto(value)


@router.post("/documents/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> DocumentResponse:
    value = await services.documents.archive_document(
        session, actor_user_id=actor.user_id, document_id=document_id
    )
    return DocumentResponse.from_dto(value)


@router.post("/document-revisions/{revision_id}/scan-result", response_model=RevisionResponse)
async def record_scan_result(
    revision_id: UUID,
    body: ScanResultRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> RevisionResponse:
    value = await services.documents.record_scan_result(
        session,
        actor_user_id=actor.user_id,
        revision_id=revision_id,
        clean=body.clean,
    )
    return RevisionResponse.from_dto(value)


@router.post("/document-revisions/{revision_id}/transition", response_model=RevisionResponse)
async def transition_revision(
    revision_id: UUID,
    body: RevisionTransitionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> RevisionResponse:
    value = await services.documents.transition_revision(
        session,
        actor_user_id=actor.user_id,
        revision_id=revision_id,
        target_status=body.target_status,
    )
    return RevisionResponse.from_dto(value)


@router.post(
    "/document-revisions/{revision_id}/preview-grants", response_model=PreviewGrantResponse
)
async def create_preview_grant(
    revision_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> PreviewGrantResponse:
    value = await services.documents.create_preview_grant(
        session,
        actor_user_id=actor.user_id,
        session_id=actor.session_id,
        revision_id=revision_id,
        device_trust=actor.device_trust,
    )
    return PreviewGrantResponse.from_dto(value)


@router.get("/document-previews/{token}", response_class=Response)
async def render_preview(
    token: str,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> Response:
    content = await services.documents.render_preview(
        session,
        actor_user_id=actor.user_id,
        session_id=actor.session_id,
        token=token,
        device_trust=actor.device_trust,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": 'inline; filename="atlas-preview.pdf"',
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/document-revisions/{revision_id}/export-requests",
    response_model=ExportRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_export(
    revision_id: UUID,
    body: ExportRequestCreateRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ExportRequestResponse:
    assert_step_up(
        action=SensitiveAction.DOCUMENT_DOWNLOAD.value,
        step_up_verified=actor.step_up_verified,
        step_up_verified_at=actor.step_up_verified_at,
    )
    value = await services.documents.request_export(
        session,
        actor_user_id=actor.user_id,
        revision_id=revision_id,
        reason=body.reason,
        device_trust=actor.device_trust,
    )
    return ExportRequestResponse.from_dto(value)


@router.post(
    "/document-export-requests/{request_id}/decision", response_model=ExportRequestResponse
)
async def decide_export(
    request_id: UUID,
    body: ExportDecisionRequest,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> ExportRequestResponse:
    assert_step_up(
        action=SensitiveAction.DOCUMENT_DOWNLOAD.value,
        step_up_verified=actor.step_up_verified,
        step_up_verified_at=actor.step_up_verified_at,
    )
    value = await services.documents.decide_export(
        session,
        actor_user_id=actor.user_id,
        request_id=request_id,
        approve=body.approve,
        decision_reason=body.decision_reason,
        device_trust=actor.device_trust,
    )
    return ExportRequestResponse.from_dto(value)


@router.get("/document-export-requests/{request_id}/content", response_class=Response)
async def download_export(
    request_id: UUID,
    actor: Annotated[SessionContext, Depends(get_current_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    services: Annotated[ApiServices, Depends(get_services)],
) -> Response:
    assert_step_up(
        action=SensitiveAction.DOCUMENT_DOWNLOAD.value,
        step_up_verified=actor.step_up_verified,
        step_up_verified_at=actor.step_up_verified_at,
    )
    content = await services.documents.download_export(
        session,
        actor_user_id=actor.user_id,
        request_id=request_id,
        device_trust=actor.device_trust,
    )
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": 'attachment; filename="atlas-controlled-export"',
            "X-Content-Type-Options": "nosniff",
        },
    )
