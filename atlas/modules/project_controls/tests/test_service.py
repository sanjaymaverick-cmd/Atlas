"""Database-free Phase 6 integrity tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.project_controls import service as service_module
from atlas.modules.project_controls.contracts import ProjectControlsConflictError
from atlas.modules.project_controls.models import MaterialReceipt, QuantityItem
from atlas.modules.project_controls.schemas import IssuanceCreate
from atlas.modules.project_controls.service import ProjectControlsService

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
    def __init__(
        self, row: object | None = None, scalars: list[object | None] | None = None
    ) -> None:
        self.row = row
        self.scalars = list(scalars or [])
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, model: object, key: UUID) -> object | None:
        return self.row

    async def scalar(self, statement: object) -> object | None:
        return self.scalars.pop(0) if self.scalars else None


async def no_audit(*args: object, **kwargs: object) -> None:
    return None


def service() -> ProjectControlsService:
    return ProjectControlsService(cast(IdentityContract, IdentityStub()))


async def test_quantity_verification_classifies_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    row = QuantityItem(
        id=uuid4(),
        project_id=uuid4(),
        cost_code_id=None,
        bim_object_id=None,
        work_package="synthetic",
        calculated_quantity=Decimal("100"),
        verified_quantity=None,
        proposed_resolution=None,
        final_approved_quantity=None,
        tolerance_pct=Decimal("2"),
        status="calculated",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    result = await service().verify_quantity(
        cast(AsyncSession, SessionStub(row)),
        actor_user_id=actor,
        quantity_id=row.id,
        verified_quantity=Decimal("101.5"),
    )
    assert result.status == "within_tolerance" and result.version == 2


async def test_material_issuance_rejects_cumulative_overdraw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    receipt = MaterialReceipt(
        id=uuid4(),
        project_id=uuid4(),
        purchase_order_id=None,
        material_id=uuid4(),
        quantity_received=Decimal("10"),
        batch_reference="SYN-BATCH",
        certificate_document_id=None,
        received_date=date(2026, 8, 17),
        status="received",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    session = SessionStub(scalars=[receipt, Decimal("8")])
    with pytest.raises(ProjectControlsConflictError, match="exceeds"):
        await service().issue_material(
            cast(AsyncSession, session),
            actor_user_id=actor,
            receipt_id=receipt.id,
            data=IssuanceCreate(Decimal("3"), date(2026, 8, 17)),
        )
    assert session.added == []


async def test_material_issuance_audit_omits_recipient_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    now = datetime.now(UTC)
    actor = uuid4()
    receipt = MaterialReceipt(
        id=uuid4(),
        project_id=uuid4(),
        purchase_order_id=None,
        material_id=uuid4(),
        quantity_received=Decimal("10"),
        batch_reference=None,
        certificate_document_id=None,
        received_date=date(2026, 8, 17),
        status="received",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    await service().issue_material(
        cast(AsyncSession, SessionStub(scalars=[receipt, Decimal("0")])),
        actor_user_id=actor,
        receipt_id=receipt.id,
        data=IssuanceCreate(Decimal("3"), date(2026, 8, 17), "SYNTHETIC PRIVATE RECIPIENT"),
    )
    assert "SYNTHETIC PRIVATE RECIPIENT" not in str(events)
