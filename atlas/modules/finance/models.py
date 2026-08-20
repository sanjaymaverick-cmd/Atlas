"""ORM mappings onto canonical Phase 9 finance tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TallyImportBatch(AuditColumns, Base):
    __tablename__ = "tally_import_batches"
    __table_args__ = {"schema": "finance"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    content_sha256: Mapped[str]
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str]
    validation_summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TallyVoucher(Base):
    __tablename__ = "tally_vouchers"
    __table_args__ = {"schema": "finance"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    import_batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_id: Mapped[str]
    voucher_type: Mapped[str]
    voucher_number: Mapped[str]
    voucher_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    ledger_reference: Mapped[str]
    currency_code: Mapped[str]
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reconciliation(AuditColumns, Base):
    __tablename__ = "reconciliations"
    __table_args__ = {"schema": "finance"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    erp_reference_type: Mapped[str]
    erp_reference_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    tally_voucher_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    discrepancy_type: Mapped[str]
    erp_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    tally_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    status: Mapped[str]
    reviewed_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_code: Mapped[str | None]
    resolution_note: Mapped[str | None]
