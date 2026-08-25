"""Documents module's published service contract and refusal types."""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.documents.schemas import (
    DocumentCreate,
    DocumentSummary,
    ExportRequestSummary,
    PreviewGrant,
    RevisionCreate,
    RevisionSummary,
)
from atlas.platform.access_control import DeviceTrust


class DocumentNotAuthorisedError(Exception):
    """The actor lacks the required permission in the document's project."""


class DocumentNotFoundError(Exception):
    """The requested document or revision does not exist."""


class DocumentConflictError(Exception):
    """The requested mutation conflicts with existing document state."""


class DocumentsContract(Protocol):
    async def get_document(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary: ...

    async def list_documents(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[DocumentSummary]: ...

    async def create_document(
        self, session: AsyncSession, *, actor_user_id: UUID, data: DocumentCreate
    ) -> DocumentSummary: ...

    async def add_revision(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        data: RevisionCreate,
    ) -> RevisionSummary: ...

    async def add_revision_content(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        revision_code: str,
        content: bytes,
        issue_purpose: str | None,
        issue_date: date | None,
    ) -> RevisionSummary: ...

    async def list_revisions(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> list[RevisionSummary]: ...

    async def archive_document(
        self, session: AsyncSession, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary: ...

    async def record_scan_result(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        clean: bool,
    ) -> RevisionSummary: ...

    async def transition_revision(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        target_status: str,
    ) -> RevisionSummary: ...

    async def create_preview_grant(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        revision_id: UUID,
        device_trust: DeviceTrust,
    ) -> PreviewGrant: ...

    async def render_preview(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        token: str,
        device_trust: DeviceTrust,
    ) -> bytes: ...

    async def request_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary: ...

    async def decide_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        approve: bool,
        decision_reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary: ...

    async def download_export(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        device_trust: DeviceTrust,
    ) -> bytes: ...
