"""Database-free Phase 8 integrity and privacy tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.commercial.contracts import CommercialContract
from atlas.modules.commercial.schemas import ContractSummary
from atlas.modules.customer_lifecycle import service as service_module
from atlas.modules.customer_lifecycle.contracts import CustomerLifecycleConflictError
from atlas.modules.customer_lifecycle.models import Booking, Collection, Installment, PaymentPlan
from atlas.modules.customer_lifecycle.schemas import BookingCreate, CollectionCreate
from atlas.modules.customer_lifecycle.service import CustomerLifecycleService
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.organization.contracts import OrganizationContract

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


class OrganizationStub:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    async def unit_belongs_to_project(
        self, session: object, *, unit_id: UUID, project_id: UUID
    ) -> bool:
        return self.valid


class CommercialStub:
    def __init__(self, contract: ContractSummary | None = None) -> None:
        self.contract = contract

    async def get_contract(
        self, session: object, *, actor_user_id: UUID, contract_id: UUID
    ) -> ContractSummary:
        assert self.contract is not None
        return self.contract


class SessionStub:
    def __init__(
        self,
        gets: dict[type[object], object] | None = None,
        scalars: list[object | None] | None = None,
    ) -> None:
        self.gets = gets or {}
        self.scalars = list(scalars or [])
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, model: type[object], key: UUID) -> object | None:
        return self.gets.get(model)

    async def scalar(self, statement: object) -> object | None:
        return self.scalars.pop(0) if self.scalars else None


def service(
    org: OrganizationStub | None = None, commercial: CommercialStub | None = None
) -> CustomerLifecycleService:
    return CustomerLifecycleService(
        cast(IdentityContract, IdentityStub()),
        cast(OrganizationContract, org or OrganizationStub()),
        cast(CommercialContract, commercial or CommercialStub()),
    )


async def no_audit(*args: object, **kwargs: object) -> None:
    return None


async def test_booking_rejects_unit_from_another_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    session = SessionStub()
    with pytest.raises(CustomerLifecycleConflictError, match="booking project"):
        await service(OrganizationStub(False)).create_booking(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            data=BookingCreate(uuid4(), uuid4(), uuid4(), date(2026, 8, 17)),
        )
    assert session.added == []


async def test_collection_audit_redacts_payment_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    now = datetime.now(UTC)
    actor = uuid4()
    booking = Booking(
        id=uuid4(),
        customer_id=uuid4(),
        unit_id=uuid4(),
        project_id=uuid4(),
        lead_id=None,
        booking_date=date(2026, 8, 17),
        booking_document_id=None,
        status="booked",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    await service().record_collection(
        cast(AsyncSession, SessionStub(gets={Booking: booking})),
        actor_user_id=actor,
        booking_id=booking.id,
        data=CollectionCreate(
            Decimal("100"), date(2026, 8, 17), "NEFT", "SYNTHETIC PRIVATE BANK REFERENCE"
        ),
    )
    assert "SYNTHETIC PRIVATE BANK REFERENCE" not in str(events)


async def test_collection_allocation_rejects_overpayment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    booking = Booking(
        id=uuid4(),
        customer_id=uuid4(),
        unit_id=uuid4(),
        project_id=uuid4(),
        lead_id=None,
        booking_date=date(2026, 8, 17),
        booking_document_id=None,
        status="booked",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    plan = PaymentPlan(
        id=uuid4(),
        booking_id=booking.id,
        plan_name=None,
        total_amount=Decimal("100"),
        status="active",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    installment = Installment(
        id=uuid4(),
        payment_plan_id=plan.id,
        due_date=date(2026, 8, 17),
        amount=Decimal("100"),
        status="pending",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    collection = Collection(
        id=uuid4(),
        booking_id=booking.id,
        installment_id=installment.id,
        amount=Decimal("30"),
        received_date=date(2026, 8, 17),
        mode=None,
        reference_number=None,
        evidence_document_id=None,
        received_by=actor,
        allocated_at=None,
        status="received",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    session = SessionStub(
        gets={Booking: booking, PaymentPlan: plan}, scalars=[collection, installment, Decimal("80")]
    )
    with pytest.raises(CustomerLifecycleConflictError, match="exceeds"):
        await service().allocate_collection(
            cast(AsyncSession, session), actor_user_id=actor, collection_id=collection.id
        )
