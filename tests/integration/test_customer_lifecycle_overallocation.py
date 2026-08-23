"""Phase 8 over-allocation and transaction integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.commercial.contracts import CommercialContract
from atlas.modules.customer_lifecycle.contracts import CustomerLifecycleConflictError
from atlas.modules.customer_lifecycle.schemas import InstallmentCreate
from atlas.modules.customer_lifecycle.service import CustomerLifecycleService
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.organization.contracts import OrganizationContract

pytestmark = [pytest.mark.integration]


class AllowAllIdentity:
    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return True


class BarrierIdentity(AllowAllIdentity):
    def __init__(self) -> None:
        self.arrivals = 0
        self.ready = asyncio.Event()
        self.lock = asyncio.Lock()

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        async with self.lock:
            self.arrivals += 1
            if self.arrivals == 2:
                self.ready.set()
        await self.ready.wait()
        return True


class UnusedDependency:
    pass


def _service(identity: AllowAllIdentity) -> CustomerLifecycleService:
    return CustomerLifecycleService(
        cast(IdentityContract, identity),
        cast(OrganizationContract, UnusedDependency()),
        cast(CommercialContract, UnusedDependency()),
    )


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_customer_plan(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    building_id, floor_id, unit_id = uuid4(), uuid4(), uuid4()
    customer_id, booking_id, plan_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Collections Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"collections-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Customer Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Customer Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Customer Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-CUST-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.buildings (id, project_id, name) "
            "VALUES (:id, :project_id, 'Synthetic Tower')"
        ),
        {"id": building_id, "project_id": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.floors (id, building_id, floor_number) "
            "VALUES (:id, :building_id, 1)"
        ),
        {"id": floor_id, "building_id": building_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.units (id, floor_id, unit_number, status) "
            "VALUES (:id, :floor_id, 'SYN-101', 'booked')"
        ),
        {"id": unit_id, "floor_id": floor_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.parties (id, party_type, legal_name, status, version) "
            "VALUES (:id, 'customer', 'Synthetic Customer', 'active', 1)"
        ),
        {"id": customer_id},
    )
    await session.execute(
        text(
            "INSERT INTO customers.customers (id, kyc_status, version) VALUES (:id, 'verified', 1)"
        ),
        {"id": customer_id},
    )
    await session.execute(
        text(
            "INSERT INTO customers.bookings "
            "(id, customer_id, unit_id, project_id, booking_date, status, version) "
            "VALUES (:id, :customer_id, :unit_id, :project_id, :booking_date, 'booked', 1)"
        ),
        {
            "id": booking_id,
            "customer_id": customer_id,
            "unit_id": unit_id,
            "project_id": project_id,
            "booking_date": date(2026, 8, 23),
        },
    )
    await session.execute(
        text(
            "INSERT INTO customers.payment_plans "
            "(id, booking_id, plan_name, total_amount, status, version) "
            "VALUES (:id, :booking_id, 'Synthetic Plan', 100, 'active', 1)"
        ),
        {"id": plan_id, "booking_id": booking_id},
    )
    await session.commit()
    return actor_id, booking_id, plan_id, project_id


async def _audit_count(session: AsyncSession) -> int:
    return int((await session.scalar(text("SELECT COUNT(*) FROM audit.audit_events"))) or 0)


async def test_installments_cannot_exceed_plan_total(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, plan_id, _ = await _seed_customer_plan(session)
        await session.execute(
            text(
                "INSERT INTO customers.payment_plan_installments "
                "(payment_plan_id, due_date, amount, status, version) "
                "VALUES (:plan_id, :due_date, 80, 'pending', 1)"
            ),
            {"plan_id": plan_id, "due_date": date(2026, 9, 1)},
        )
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="exceed"):
            await _service(AllowAllIdentity()).add_installment(
                session,
                actor_user_id=actor_id,
                plan_id=plan_id,
                data=InstallmentCreate(date(2026, 10, 1), Decimal("30")),
            )

        total = await session.scalar(
            text(
                "SELECT COALESCE(SUM(amount), 0) FROM customers.payment_plan_installments "
                "WHERE payment_plan_id = :plan_id"
            ),
            {"plan_id": plan_id},
        )
        assert Decimal(total or 0) == Decimal("80")
        assert await _audit_count(session) == 0


async def test_concurrent_installments_are_serialized_at_the_plan(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, _, plan_id, _ = await _seed_customer_plan(seed)

    identity = BarrierIdentity()

    async def add_installment(due_date: date) -> str:
        async with session_factory() as session:
            try:
                await _service(identity).add_installment(
                    session,
                    actor_user_id=actor_id,
                    plan_id=plan_id,
                    data=InstallmentCreate(due_date, Decimal("60")),
                )
                await session.commit()
                return "created"
            except CustomerLifecycleConflictError:
                await session.rollback()
                return "conflict"

    results = await asyncio.gather(
        add_installment(date(2026, 9, 1)), add_installment(date(2026, 10, 1))
    )
    assert sorted(results) == ["conflict", "created"]
    async with session_factory() as session:
        total = await session.scalar(
            text(
                "SELECT COALESCE(SUM(amount), 0) FROM customers.payment_plan_installments "
                "WHERE payment_plan_id = :plan_id"
            ),
            {"plan_id": plan_id},
        )
        assert Decimal(total or 0) == Decimal("60")
        assert await _audit_count(session) == 1


async def test_collection_allocation_cannot_exceed_installment(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, plan_id, _ = await _seed_customer_plan(session)
        installment_id, allocated_id, received_id = uuid4(), uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO customers.payment_plan_installments "
                "(id, payment_plan_id, due_date, amount, status, version) "
                "VALUES (:id, :plan_id, :due_date, 100, 'pending', 1)"
            ),
            {"id": installment_id, "plan_id": plan_id, "due_date": date(2026, 9, 1)},
        )
        await session.execute(
            text(
                "INSERT INTO customers.collections "
                "(id, booking_id, installment_id, amount, received_date, status, version) "
                "VALUES (:allocated_id, :booking_id, :installment_id, 80, :received_date, "
                "'allocated', 1), "
                "(:received_id, :booking_id, :installment_id, 30, :received_date, 'received', 1)"
            ),
            {
                "allocated_id": allocated_id,
                "received_id": received_id,
                "booking_id": booking_id,
                "installment_id": installment_id,
                "received_date": date(2026, 8, 23),
            },
        )
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="exceeds"):
            await _service(AllowAllIdentity()).allocate_collection(
                session, actor_user_id=actor_id, collection_id=received_id
            )

        state = (
            await session.execute(
                text("SELECT status, version FROM customers.collections WHERE id = :id"),
                {"id": received_id},
            )
        ).one()
        assert tuple(state) == ("received", 1)
        assert await _audit_count(session) == 0
