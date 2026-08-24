"""Validated HTTP models for Phase 9 finance reconciliation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.finance.schemas import (
    ExternalVoucherCreate,
    LedgerSyncBatchCreate,
    ReconciliationCreate,
    ReconciliationReview,
)


class DtoResponse(BaseModel):
    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(**{f: getattr(value, f) for f in cls.model_fields})


class LedgerSyncBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_document_id: UUID
    content_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    period_start: date | None = None
    period_end: date | None = None

    def to_dto(self, legal_entity_id: UUID) -> LedgerSyncBatchCreate:
        return LedgerSyncBatchCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class LedgerSyncBatchResponse(DtoResponse):
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


class ExternalVoucherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=200)
    voucher_type: str = Field(min_length=1, max_length=100)
    voucher_number: str = Field(min_length=1, max_length=200)
    voucher_date: date
    amount: Decimal = Field(ge=0)
    ledger_reference: str = Field(min_length=1, max_length=300)
    currency_code: str = Field(default="INR", pattern="^[A-Z]{3}$")
    project_id: UUID | None = None

    def to_dto(self) -> ExternalVoucherCreate:
        return ExternalVoucherCreate(**self.model_dump())


class ExternalVoucherResponse(DtoResponse):
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


class ReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atlas_reference_type: str = Field(min_length=1, max_length=100)
    atlas_reference_id: UUID
    discrepancy_type: str = Field(
        pattern="^(missing_in_external_ledger|missing_in_atlas|amount_mismatch|wrong_entity|wrong_project|duplicate_voucher|unallocated_receipt|schedule_not_updated|obligation_still_open)$"
    )
    external_voucher_id: UUID | None = None
    atlas_amount: Decimal | None = Field(default=None, ge=0)
    external_amount: Decimal | None = Field(default=None, ge=0)

    def to_dto(self, legal_entity_id: UUID) -> ReconciliationCreate:
        return ReconciliationCreate(legal_entity_id=legal_entity_id, **self.model_dump())


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(pattern="^(under_review|reconciled|accepted_exception)$")
    resolution_code: str | None = Field(default=None, max_length=100)
    resolution_note: str | None = Field(default=None, max_length=1000)

    def to_dto(self) -> ReconciliationReview:
        return ReconciliationReview(**self.model_dump())


class ReconciliationResponse(DtoResponse):
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
