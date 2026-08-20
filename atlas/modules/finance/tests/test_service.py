"""Database-free Phase 9 integrity and privacy tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.finance import service as service_module
from atlas.modules.finance.contracts import FinanceConflictError
from atlas.modules.finance.models import Reconciliation, TallyImportBatch
from atlas.modules.finance.schemas import ImportBatchCreate, ReconciliationReview, VoucherCreate
from atlas.modules.finance.service import FinanceService
from atlas.modules.identity.contracts import IdentityContract

pytestmark = pytest.mark.unit


class IdentityStub:
    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return True


class SessionStub:
    def __init__(self, gets: dict[type[object], object] | None = None) -> None:
        self.gets = gets or {}
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, model: type[object], key: UUID) -> object | None:
        return self.gets.get(model)

    async def scalar(self, statement: object) -> object | None:
        return next(iter(self.gets.values()), None)


def service() -> FinanceService:
    return FinanceService(cast(IdentityContract, IdentityStub()))


async def no_audit(*args: object, **kwargs: object) -> None:
    return None


def batch(actor: UUID) -> TallyImportBatch:
    now = datetime.now(UTC)
    return TallyImportBatch(
        id=uuid4(),
        legal_entity_id=uuid4(),
        source_document_id=uuid4(),
        content_sha256="a" * 64,
        period_start=None,
        period_end=None,
        status="validated",
        validation_summary={"schema_valid": True},
        imported_at=None,
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=2,
        archived_at=None,
    )


async def test_import_batch_rejects_non_sha256_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    with pytest.raises(FinanceConflictError, match="SHA-256"):
        await service().create_import_batch(
            cast(AsyncSession, SessionStub()),
            actor_user_id=uuid4(),
            data=ImportBatchCreate(uuid4(), uuid4(), "not-a-digest"),
        )


async def test_voucher_audit_redacts_ledger_and_voucher_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    actor = uuid4()
    row = batch(actor)
    await service().import_voucher(
        cast(AsyncSession, SessionStub({TallyImportBatch: row})),
        actor_user_id=actor,
        batch_id=row.id,
        data=VoucherCreate(
            "SYN-EXT-1",
            "Receipt",
            "SYN-PRIVATE-VOUCHER",
            date(2026, 8, 17),
            Decimal("100"),
            "SYN-PRIVATE-LEDGER",
        ),
    )
    assert "SYN-PRIVATE-VOUCHER" not in str(events)
    assert "SYN-PRIVATE-LEDGER" not in str(events)


async def test_final_review_requires_resolution_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    actor = uuid4()
    now = datetime.now(UTC)
    row = Reconciliation(
        id=uuid4(),
        legal_entity_id=uuid4(),
        erp_reference_type="collection",
        erp_reference_id=uuid4(),
        tally_voucher_id=None,
        discrepancy_type="missing_in_tally",
        erp_amount=Decimal("100"),
        tally_amount=None,
        status="under_review",
        reviewed_by=actor,
        reviewed_at=now,
        resolution_code=None,
        resolution_note=None,
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=2,
        archived_at=None,
    )
    with pytest.raises(FinanceConflictError, match="resolution code"):
        await service().review_reconciliation(
            cast(AsyncSession, SessionStub({Reconciliation: row})),
            actor_user_id=actor,
            reconciliation_id=row.id,
            data=ReconciliationReview("reconciled"),
        )
