"""Audited Phase 9 external-ledger reconciliation workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.finance.contracts import (
    FinanceConflictError,
    FinanceNotAuthorisedError,
    FinanceNotFoundError,
)
from atlas.modules.finance.models import ExternalVoucher, LedgerSyncBatch, Reconciliation
from atlas.modules.finance.schemas import (
    ExternalVoucherCreate,
    ExternalVoucherSummary,
    LedgerSyncBatchCreate,
    LedgerSyncBatchSummary,
    ReconciliationCreate,
    ReconciliationReview,
    ReconciliationSummary,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

DISCREPANCIES = frozenset(
    {
        "missing_in_external_ledger",
        "missing_in_atlas",
        "amount_mismatch",
        "wrong_entity",
        "wrong_project",
        "duplicate_voucher",
        "unallocated_receipt",
        "schedule_not_updated",
        "obligation_still_open",
    }
)
REVIEW_TRANSITIONS = {
    "open": frozenset({"under_review"}),
    "under_review": frozenset({"reconciled", "accepted_exception"}),
}


def batch_summary(row: LedgerSyncBatch) -> LedgerSyncBatchSummary:
    return LedgerSyncBatchSummary(
        row.id,
        row.provider,
        row.legal_entity_id,
        row.source_document_id,
        row.content_sha256,
        row.period_start,
        row.period_end,
        row.status,
        row.imported_at,
        row.version,
    )


def voucher_summary(row: ExternalVoucher) -> ExternalVoucherSummary:
    return ExternalVoucherSummary(
        row.id,
        row.sync_batch_id,
        row.legal_entity_id,
        row.project_id,
        row.external_id,
        row.voucher_type,
        row.voucher_number,
        row.voucher_date,
        row.amount,
        row.currency_code,
        row.status,
        row.version,
    )


def reconciliation_summary(row: Reconciliation) -> ReconciliationSummary:
    return ReconciliationSummary(
        row.id,
        row.legal_entity_id,
        row.atlas_reference_type,
        row.atlas_reference_id,
        row.external_voucher_id,
        row.discrepancy_type,
        row.atlas_amount,
        row.external_amount,
        row.status,
        row.reviewed_by,
        row.reviewed_at,
        row.resolution_code,
        row.version,
    )


PERM_READ = "finance.read"


class FinanceService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(self, s: AsyncSession, actor: UUID, permission: str, entity: UUID) -> None:
        if not await self._identity.check_scoped_role(
            s, user_id=actor, permission_code=permission, legal_entity_id=entity
        ):
            raise FinanceNotAuthorisedError(f"user may not {permission} in requested scope")

    async def _audit(
        self,
        s: AsyncSession,
        actor: UUID,
        table: str,
        row: UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
    ) -> None:
        await record_event(
            s,
            actor_user_id=actor,
            entity_schema="finance",
            entity_table=table,
            entity_id=row,
            action=action,
            before_state=before,
            after_state=after,
        )

    async def _batch(self, s: AsyncSession, batch_id: UUID) -> LedgerSyncBatch:
        row = await s.scalar(
            select(LedgerSyncBatch).where(LedgerSyncBatch.id == batch_id).with_for_update()
        )
        if row is None or row.archived_at is not None:
            raise FinanceNotFoundError(f"ledger sync batch {batch_id} does not exist")
        return row

    async def create_sync_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, data: LedgerSyncBatchCreate
    ) -> LedgerSyncBatchSummary:
        await self._require(s, actor_user_id, "finance.ledger.sync", data.legal_entity_id)
        if len(data.content_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in data.content_sha256
        ):
            raise FinanceConflictError("content digest must be lowercase SHA-256")
        if data.period_start and data.period_end and data.period_end < data.period_start:
            raise FinanceConflictError("sync period end precedes start")
        now = datetime.now(UTC)
        row = LedgerSyncBatch(
            id=uuid4(),
            provider="erpnext",
            legal_entity_id=data.legal_entity_id,
            source_document_id=data.source_document_id,
            content_sha256=data.content_sha256,
            period_start=data.period_start,
            period_end=data.period_end,
            status="pending_validation",
            validation_summary={},
            imported_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise FinanceConflictError(
                "external-ledger export content was already registered"
            ) from exc
        await self._audit(
            s,
            actor_user_id,
            "ledger_sync_batches",
            row.id,
            "create",
            None,
            {
                "legal_entity_id": str(row.legal_entity_id),
                "source_document_id": str(row.source_document_id),
                "digest_recorded": True,
                "status": row.status,
                "version": 1,
            },
        )
        return batch_summary(row)

    async def validate_sync_batch(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID
    ) -> LedgerSyncBatchSummary:
        row = await self._batch(s, batch_id)
        await self._require(s, actor_user_id, "finance.ledger.validate", row.legal_entity_id)
        if row.status != "pending_validation":
            raise FinanceConflictError("only a pending sync batch may be validated")
        existing_voucher = await s.scalar(
            select(ExternalVoucher.id).where(ExternalVoucher.sync_batch_id == row.id).limit(1)
        )
        if existing_voucher is not None:
            raise FinanceConflictError("sync batch already contains vouchers")
        before = {"status": row.status, "version": row.version}
        row.status = "validated"
        row.validation_summary = {"schema_valid": True}
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "ledger_sync_batches",
            row.id,
            "validate",
            before,
            {"status": row.status, "schema_valid": True, "version": row.version},
        )
        return batch_summary(row)

    async def record_external_voucher(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID, data: ExternalVoucherCreate
    ) -> ExternalVoucherSummary:
        batch = await self._batch(s, batch_id)
        await self._require(s, actor_user_id, "finance.ledger.sync", batch.legal_entity_id)
        if (
            batch.status not in {"validated", "imported"}
            or data.amount < 0
            or len(data.currency_code) != 3
            or not data.currency_code.isupper()
        ):
            raise FinanceConflictError("voucher or sync batch is invalid")
        now = datetime.now(UTC)
        row = ExternalVoucher(
            id=uuid4(),
            sync_batch_id=batch.id,
            legal_entity_id=batch.legal_entity_id,
            project_id=data.project_id,
            external_id=data.external_id,
            voucher_type=data.voucher_type,
            voucher_number=data.voucher_number,
            voucher_date=data.voucher_date,
            amount=data.amount,
            ledger_reference=data.ledger_reference,
            currency_code=data.currency_code,
            imported_at=now,
            status="imported",
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise FinanceConflictError(
                "voucher external ID already exists for legal entity"
            ) from exc
        if batch.status == "validated":
            batch_before = {"status": batch.status, "version": batch.version}
            batch.status = "imported"
            batch.imported_at = now
            batch.updated_at = now
            batch.updated_by = actor_user_id
            batch.version += 1
            await self._audit(
                s,
                actor_user_id,
                "ledger_sync_batches",
                batch.id,
                "import",
                batch_before,
                {"status": batch.status, "imported_at_recorded": True, "version": batch.version},
            )
        await self._audit(
            s,
            actor_user_id,
            "external_vouchers",
            row.id,
            "import",
            None,
            {
                "sync_batch_id": str(batch.id),
                "legal_entity_id": str(batch.legal_entity_id),
                "project_id": str(row.project_id) if row.project_id else None,
                "amount": str(row.amount),
                "currency_code": row.currency_code,
                "ledger_reference_recorded": True,
                "voucher_number_recorded": True,
                "status": row.status,
                "version": 1,
            },
        )
        return voucher_summary(row)

    async def create_reconciliation(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ReconciliationCreate
    ) -> ReconciliationSummary:
        await self._require(s, actor_user_id, "finance.reconciliation.create", data.legal_entity_id)
        if (
            data.discrepancy_type not in DISCREPANCIES
            or (data.atlas_amount is not None and data.atlas_amount < 0)
            or (data.external_amount is not None and data.external_amount < 0)
        ):
            raise FinanceConflictError("reconciliation discrepancy is invalid")
        now = datetime.now(UTC)
        row = Reconciliation(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            atlas_reference_type=data.atlas_reference_type,
            atlas_reference_id=data.atlas_reference_id,
            external_voucher_id=data.external_voucher_id,
            discrepancy_type=data.discrepancy_type,
            atlas_amount=data.atlas_amount,
            external_amount=data.external_amount,
            status="open",
            reviewed_by=None,
            reviewed_at=None,
            resolution_code=None,
            resolution_note=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise FinanceConflictError("reconciliation fact already exists") from exc
        await self._audit(
            s,
            actor_user_id,
            "reconciliations",
            row.id,
            "create",
            None,
            {
                "legal_entity_id": str(row.legal_entity_id),
                "atlas_reference_type": row.atlas_reference_type,
                "atlas_reference_id": str(row.atlas_reference_id),
                "external_voucher_id": str(row.external_voucher_id)
                if row.external_voucher_id
                else None,
                "discrepancy_type": row.discrepancy_type,
                "atlas_amount": str(row.atlas_amount) if row.atlas_amount is not None else None,
                "external_amount": str(row.external_amount)
                if row.external_amount is not None
                else None,
                "status": row.status,
                "version": 1,
            },
        )
        return reconciliation_summary(row)

    async def review_reconciliation(
        self,
        s: AsyncSession,
        *,
        actor_user_id: UUID,
        reconciliation_id: UUID,
        data: ReconciliationReview,
    ) -> ReconciliationSummary:
        row = await s.scalar(
            select(Reconciliation).where(Reconciliation.id == reconciliation_id).with_for_update()
        )
        if row is None or row.archived_at is not None:
            raise FinanceNotFoundError(f"reconciliation {reconciliation_id} does not exist")
        await self._require(s, actor_user_id, "finance.reconciliation.review", row.legal_entity_id)
        if data.target_status not in REVIEW_TRANSITIONS.get(row.status, frozenset()):
            raise FinanceConflictError(
                f"reconciliation cannot move from {row.status} to {data.target_status}"
            )
        if data.target_status in {"reconciled", "accepted_exception"} and not data.resolution_code:
            raise FinanceConflictError("final review requires a resolution code")
        before = {"status": row.status, "version": row.version}
        row.status = data.target_status
        row.reviewed_by = actor_user_id
        row.reviewed_at = datetime.now(UTC)
        row.resolution_code = data.resolution_code
        row.resolution_note = data.resolution_note
        row.updated_at = row.reviewed_at
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "reconciliations",
            row.id,
            "review",
            before,
            {
                "status": row.status,
                "reviewed_by": str(actor_user_id),
                "resolution_code": row.resolution_code,
                "resolution_note_recorded": row.resolution_note is not None,
                "version": row.version,
            },
        )
        return reconciliation_summary(row)

    # -- reads ------------------------------------------------------------
    # Added 2026-08-20; this module previously published writes only.
    #
    # Finance is scoped by legal entity, not project: ERPNext is the statutory
    # book of record per entity, and reconciliation is an entity-level activity.
    # Vouchers are read through their batch so a caller cannot enumerate
    # another entity's ledger by guessing batch ids.

    async def _batch_or_refuse(self, s: AsyncSession, batch_id: UUID) -> LedgerSyncBatch:
        row = await s.get(LedgerSyncBatch, batch_id)
        if row is None:
            raise FinanceNotFoundError(f"sync batch {batch_id} does not exist")
        return row

    async def list_sync_batches(
        self, s: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[LedgerSyncBatchSummary]:
        await self._require(s, actor_user_id, PERM_READ, legal_entity_id)
        result = await s.execute(
            select(LedgerSyncBatch)
            .where(LedgerSyncBatch.legal_entity_id == legal_entity_id)
            .where(LedgerSyncBatch.archived_at.is_(None))
            .order_by(LedgerSyncBatch.created_at)
        )
        return [batch_summary(row) for row in result.scalars()]

    async def list_external_vouchers(
        self, s: AsyncSession, *, actor_user_id: UUID, batch_id: UUID
    ) -> list[ExternalVoucherSummary]:
        batch = await self._batch_or_refuse(s, batch_id)
        await self._require(s, actor_user_id, PERM_READ, batch.legal_entity_id)
        result = await s.execute(
            select(ExternalVoucher)
            .where(ExternalVoucher.sync_batch_id == batch_id)
            .order_by(ExternalVoucher.voucher_date)
        )
        return [voucher_summary(row) for row in result.scalars()]

    async def list_reconciliations(
        self, s: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[ReconciliationSummary]:
        await self._require(s, actor_user_id, PERM_READ, legal_entity_id)
        result = await s.execute(
            select(Reconciliation)
            .where(Reconciliation.legal_entity_id == legal_entity_id)
            .where(Reconciliation.archived_at.is_(None))
            .order_by(Reconciliation.created_at)
        )
        return [reconciliation_summary(row) for row in result.scalars()]
