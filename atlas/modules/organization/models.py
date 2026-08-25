"""ORM mappings onto the ``organization`` schema.

Private to this module.

Phase 1 scope only: business groups, legal entities and projects. The
``buildings``, ``floors``, ``units``, ``parties``, ``vendors`` and
``contractors`` tables exist in ``db/schema.sql`` for later phases and are
deliberately unmapped — mapping a table implies a module owns it, and nothing
owns those yet.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class BusinessGroup(Base):
    __tablename__ = "business_groups"
    __table_args__ = {"schema": "organization"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalEntity(Base):
    """A legal entity. The unit of separation in Blueprint §2."""

    __tablename__ = "legal_entities"
    __table_args__ = {"schema": "organization"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    business_group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organization.business_groups.id")
    )
    name: Mapped[str] = mapped_column(String)
    registration_number: Mapped[str | None] = mapped_column(String)
    entity_type: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Project(Base):
    """A project. The unit of isolation in Blueprint §2.

    ``version`` is incremented on every update and ``archived_at`` is set
    instead of deleting — §2's "no silent overwrites" applies to business
    records as well as to the audit log.
    """

    __tablename__ = "projects"
    __table_args__ = {"schema": "organization"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organization.legal_entities.id")
    )
    name: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String, unique=True)
    city: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    start_date: Mapped[date | None] = mapped_column(Date)
    target_completion_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
