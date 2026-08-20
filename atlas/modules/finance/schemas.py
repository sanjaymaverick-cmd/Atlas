"""Published immutable Phase 9 finance DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ImportBatchCreate:
    legal_entity_id: UUID
    source_document_id: UUID
    content_sha256: str
    period_start: date | None = None
    period_end: date | None = None


@dataclass(frozen=True, slots=True)
class ImportBatchSummary:
    id: UUID
    legal_entity_id: UUID
    source_document_id: UUID
    content_sha256: str
    period_start: date | None
    period_end: date | None
    status: str
    imported_at: datetime | None
    version: int


@dataclass(frozen=True, slots=True)
class VoucherCreate:
    external_id: str
    voucher_type: str
    voucher_number: str
    voucher_date: date
    amount: Decimal
    ledger_reference: str
    currency_code: str = "INR"
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class VoucherSummary:
    id: UUID
    import_batch_id: UUID
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
    erp_reference_type: str
    erp_reference_id: UUID
    discrepancy_type: str
    tally_voucher_id: UUID | None = None
    erp_amount: Decimal | None = None
    tally_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationReview:
    target_status: str
    resolution_code: str | None = None
    resolution_note: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    id: UUID
    legal_entity_id: UUID
    erp_reference_type: str
    erp_reference_id: UUID
    tally_voucher_id: UUID | None
    discrepancy_type: str
    erp_amount: Decimal | None
    tally_amount: Decimal | None
    status: str
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    resolution_code: str | None
    version: int
