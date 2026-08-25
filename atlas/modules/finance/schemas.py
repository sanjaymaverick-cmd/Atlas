"""Published immutable Phase 9 finance DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LedgerSyncBatchCreate:
    legal_entity_id: UUID
    source_document_id: UUID
    content_sha256: str
    period_start: date | None = None
    period_end: date | None = None


@dataclass(frozen=True, slots=True)
class LedgerSyncBatchSummary:
    id: UUID
    provider: str
    legal_entity_id: UUID
    source_document_id: UUID
    content_sha256: str
    period_start: date | None
    period_end: date | None
    status: str
    imported_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class ExternalVoucherCreate:
    external_id: str
    voucher_type: str
    voucher_number: str
    voucher_date: date
    amount: Decimal
    ledger_reference: str
    currency_code: str = "INR"
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ExternalVoucherSummary:
    id: UUID
    sync_batch_id: UUID
    legal_entity_id: UUID
    project_id: UUID | None
    external_id: str
    voucher_type: str
    voucher_number: str
    voucher_date: date
    amount: Decimal
    currency_code: str
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class ReconciliationCreate:
    legal_entity_id: UUID
    atlas_reference_type: str
    atlas_reference_id: UUID
    discrepancy_type: str
    external_voucher_id: UUID | None = None
    atlas_amount: Decimal | None = None
    external_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationReview:
    target_status: str
    resolution_code: str | None = None
    resolution_note: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    id: UUID
    legal_entity_id: UUID
    atlas_reference_type: str
    atlas_reference_id: UUID
    external_voucher_id: UUID | None
    discrepancy_type: str
    atlas_amount: Decimal | None
    external_amount: Decimal | None
    status: str
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    resolution_code: str | None
    version: int
