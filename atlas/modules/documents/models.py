"""ORM mappings onto the canonical ``documents`` schema."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "documents"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organization.projects.id")
    )
    building_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    floor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    unit_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    discipline: Mapped[str | None] = mapped_column(String)
    drawing_number: Mapped[str | None] = mapped_column(String)
    document_type: Mapped[str | None] = mapped_column(String)
    classification: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = {"schema": "documents"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.documents.id")
    )
    revision_code: Mapped[str] = mapped_column(String)
    issue_purpose: Mapped[str | None] = mapped_column(String)
    issue_date: Mapped[date | None] = mapped_column(Date)
    author_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reviewer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    approver_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    superseded_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    related_change_request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    object_storage_key: Mapped[str] = mapped_column(String)
    checksum_sha256: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PreviewGrantRecord(Base):
    __tablename__ = "preview_grants"
    __table_args__ = {"schema": "documents"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.document_versions.id")
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.sessions.id")
    )
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.users.id"))
    token_hash: Mapped[str] = mapped_column(String)
    watermark_text: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExportRequest(Base):
    __tablename__ = "export_requests"
    __table_args__ = {"schema": "documents"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.document_versions.id")
    )
    requested_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id")
    )
    approved_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String)
    decision_reason: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int]
