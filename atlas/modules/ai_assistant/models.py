"""ORM mappings onto privacy-minimized AI safety tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class AiQuery(Base):
    __tablename__ = "ai_queries"
    __table_args__ = {"schema": "ai"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    legal_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_digest: Mapped[str]
    request_length: Mapped[int]
    intent_classification: Mapped[str]
    authority_level: Mapped[int]
    response_digest: Mapped[str | None]
    response_length: Mapped[int | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    required_approver: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthorityLog(Base):
    __tablename__ = "ai_authority_log"
    __table_args__ = {"schema": "ai"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    ai_query_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    authority_level: Mapped[int]
    action_code: Mapped[str]
    blocked: Mapped[bool]
    reason_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
