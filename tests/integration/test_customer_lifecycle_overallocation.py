"""Phase 8 over-allocation and transaction integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.commercial.contracts import CommercialContract
from atlas.modules.commercial.service import CommercialService
from atlas.modules.customer_lifecycle import service as service_module
from atlas.modules.customer_lifecycle.contracts import CustomerLifecycleConflictError
from atlas.modules.customer_lifecycle.schemas import (
    CollectionCreate,
    InstallmentCreate,
    PossessionTransition,
    RegistrationTransition,
)
from atlas.modules.customer_lifecycle.service import CustomerLifecycleService
from atlas.modules.documents.service import DocumentsService
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


def _service(
    identity: AllowAllIdentity, documents: DocumentsService | None = None
) -> CustomerLifecycleService:
    return CustomerLifecycleService(
        cast(IdentityContract, identity),
        cast(OrganizationContract, UnusedDependency()),
        cast(CommercialContract, UnusedDependency()),
        documents,
    )


def _link_service(identity: AllowAllIdentity) -> CustomerLifecycleService:
    documents = DocumentsService(identity)
    commercial = CommercialService(identity, documents)
    return CustomerLifecycleService(
        cast(IdentityContract, identity),
        cast(OrganizationContract, UnusedDependency()),
        commercial,
        documents,
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


async def _seed_document(
    session: AsyncSession, *, actor_id: UUID, project_id: UUID, status: str = "approved"
) -> UUID:
    document_id, revision_id = uuid4(), uuid4()
    document_status = status if status in {"approved", "issued"} else "under_review"
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, created_by, updated_by, "
            "version) VALUES (:id, :project_id, 'customer_evidence', 'restricted', "
            ":document_status, "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": document_id,
            "project_id": project_id,
            "document_status": document_status,
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO documents.document_versions "
            "(id, document_id, revision_code, object_storage_key, checksum_sha256, status, "
            "author_id) VALUES (:id, :document_id, 'SYN-1', :object_key, :checksum, :status, "
            ":actor_id)"
        ),
        {
            "id": revision_id,
            "document_id": document_id,
            "object_key": f"synthetic/customer-evidence/{revision_id}.pdf",
            "checksum": "e" * 64,
            "status": status,
            "actor_id": actor_id,
        },
    )
    return document_id


async def _seed_contract_for_booking(
    session: AsyncSession,
    *,
    actor_id: UUID,
    booking_id: UUID,
    project_matches: bool,
    customer_matches: bool,
    status: str,
    with_evidence: bool,
) -> UUID:
    booking = (
        await session.execute(
            text(
                "SELECT b.project_id, b.customer_id, p.legal_entity_id "
                "FROM customers.bookings b "
                "JOIN organization.projects p ON p.id = b.project_id "
                "WHERE b.id = :id"
            ),
            {"id": booking_id},
        )
    ).one()
    project_id, customer_id, entity_id = booking
    if not project_matches:
        project_id = uuid4()
        await session.execute(
            text(
                "INSERT INTO organization.projects "
                "(id, legal_entity_id, name, code, status, version) "
                "VALUES (:id, :entity_id, 'Synthetic Other Project', :code, 'active', 1)"
            ),
            {"id": project_id, "entity_id": entity_id, "code": f"SYN-OTHER-{project_id}"},
        )
    if not customer_matches:
        customer_id = uuid4()
        await session.execute(
            text(
                "INSERT INTO organization.parties "
                "(id, party_type, legal_name, status, version) "
                "VALUES (:id, 'customer', 'Synthetic Other Customer', 'active', 1)"
            ),
            {"id": customer_id},
        )

    document_id: UUID | None = None
    if with_evidence:
        document_id, revision_id = uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO documents.documents "
                "(id, project_id, document_type, classification, status, created_by, "
                "updated_by, version) VALUES "
                "(:id, :project_id, 'executed_contract', 'restricted', 'approved', "
                ":actor_id, :actor_id, 1)"
            ),
            {"id": document_id, "project_id": project_id, "actor_id": actor_id},
        )
        await session.execute(
            text(
                "INSERT INTO documents.document_versions "
                "(id, document_id, revision_code, object_storage_key, checksum_sha256, "
                "status, author_id) VALUES "
                "(:id, :document_id, 'SYN-1', :object_key, :checksum, 'approved', :actor_id)"
            ),
            {
                "id": revision_id,
                "document_id": document_id,
                "object_key": f"synthetic/customer-contracts/{revision_id}.pdf",
                "checksum": "d" * 64,
                "actor_id": actor_id,
            },
        )

    contract_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO contracts.contracts "
            "(id, project_id, party_id, contract_type, value, status, execution_method, "
            "executed_at, executed_document_id, created_by, updated_by, version) VALUES "
            "(:id, :project_id, :party_id, 'customer_sale', 100, :status, "
            ":method, CASE WHEN :executed THEN now() ELSE NULL END, :document_id, "
            ":actor_id, :actor_id, 5)"
        ),
        {
            "id": contract_id,
            "project_id": project_id,
            "party_id": customer_id,
            "status": status,
            "method": "synthetic-esign" if status == "executed" else None,
            "executed": status == "executed",
            "document_id": document_id,
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return contract_id


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


@pytest.mark.parametrize(
    ("project_matches", "customer_matches", "status", "with_evidence"),
    [
        (False, True, "executed", True),
        (True, False, "executed", True),
        (True, True, "approved", False),
        (True, True, "executed", False),
    ],
)
async def test_booking_refuses_invalid_contract_linkage(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_matches: bool,
    customer_matches: bool,
    status: str,
    with_evidence: bool,
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        contract_id = await _seed_contract_for_booking(
            session,
            actor_id=actor_id,
            booking_id=booking_id,
            project_matches=project_matches,
            customer_matches=customer_matches,
            status=status,
            with_evidence=with_evidence,
        )

        with pytest.raises(CustomerLifecycleConflictError):
            await _link_service(AllowAllIdentity()).link_executed_contract(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                contract_id=contract_id,
            )
        await session.rollback()

        linked = await session.scalar(
            text("SELECT COUNT(*) FROM customers.booking_contracts WHERE booking_id = :id"),
            {"id": booking_id},
        )
        assert linked == 0
        assert await _audit_count(session) == 0


async def test_booking_links_matching_executed_contract_with_one_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        contract_id = await _seed_contract_for_booking(
            session,
            actor_id=actor_id,
            booking_id=booking_id,
            project_matches=True,
            customer_matches=True,
            status="executed",
            with_evidence=True,
        )

        linked = await _link_service(AllowAllIdentity()).link_executed_contract(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            contract_id=contract_id,
        )
        await session.commit()

        assert linked.booking_id == booking_id
        assert linked.contract_id == contract_id
        assert await _audit_count(session) == 1


async def test_collection_refuses_installment_from_another_booking(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        _, _, other_plan_id, _ = await _seed_customer_plan(session)
        installment_id = uuid4()
        await session.execute(
            text(
                "INSERT INTO customers.payment_plan_installments "
                "(id, payment_plan_id, due_date, amount, status, version) "
                "VALUES (:id, :plan_id, :due_date, 100, 'pending', 1)"
            ),
            {"id": installment_id, "plan_id": other_plan_id, "due_date": date(2026, 9, 1)},
        )
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="does not belong"):
            await _service(AllowAllIdentity()).record_collection(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                data=CollectionCreate(
                    amount=Decimal("10"),
                    received_date=date(2026, 8, 24),
                    installment_id=installment_id,
                ),
            )
        await session.rollback()
        assert (
            await session.scalar(
                text("SELECT COUNT(*) FROM customers.collections WHERE booking_id = :id"),
                {"id": booking_id},
            )
            == 0
        )
        assert await _audit_count(session) == 0


async def test_collection_refuses_cross_project_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        other_actor, _, _, other_project = await _seed_customer_plan(session)
        document_id = await _seed_document(session, actor_id=other_actor, project_id=other_project)
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="in project"):
            await _service(
                AllowAllIdentity(), DocumentsService(AllowAllIdentity())
            ).record_collection(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                data=CollectionCreate(
                    amount=Decimal("10"),
                    received_date=date(2026, 8, 24),
                    evidence_document_id=document_id,
                ),
            )
        await session.rollback()
        assert (
            await session.scalar(
                text("SELECT COUNT(*) FROM customers.collections WHERE booking_id = :id"),
                {"id": booking_id},
            )
            == 0
        )
        assert await _audit_count(session) == 0


async def test_database_refuses_cross_project_booking_document(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        _, booking_id, _, _ = await _seed_customer_plan(session)
        other_actor, _, _, other_project = await _seed_customer_plan(session)
        document_id = await _seed_document(session, actor_id=other_actor, project_id=other_project)
        await session.commit()

        with pytest.raises(IntegrityError) as violation:
            await session.execute(
                text(
                    "UPDATE customers.bookings SET booking_document_id = :document_id "
                    "WHERE id = :booking_id"
                ),
                {"document_id": document_id, "booking_id": booking_id},
            )
        assert (
            violation.value.orig.diag.constraint_name  # type: ignore[union-attr]
            == "fk_bookings_document_project"
        )
        await session.rollback()


async def test_booking_with_downstream_records_cannot_be_cancelled_directly(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        with pytest.raises(CustomerLifecycleConflictError, match="cannot be cancelled directly"):
            await _service(AllowAllIdentity()).cancel_booking(
                session, actor_user_id=actor_id, booking_id=booking_id
            )
        await session.rollback()
        state = (
            await session.execute(
                text("SELECT status, version FROM customers.bookings WHERE id = :id"),
                {"id": booking_id},
            )
        ).one()
        assert tuple(state) == ("booked", 1)
        assert await _audit_count(session) == 0


async def test_concurrent_registration_transition_has_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, booking_id, _, _ = await _seed_customer_plan(seed)

    identity = AllowAllIdentity()
    arrivals = 0
    ready = asyncio.Event()
    arrival_lock = asyncio.Lock()

    async def schedule() -> str:
        nonlocal arrivals
        async with session_factory() as session:
            async with arrival_lock:
                arrivals += 1
                if arrivals == 2:
                    ready.set()
            await ready.wait()
            try:
                await _service(identity).transition_registration(
                    session,
                    actor_user_id=actor_id,
                    booking_id=booking_id,
                    data=RegistrationTransition("scheduled"),
                )
                await session.commit()
                return "scheduled"
            except (CustomerLifecycleConflictError, IntegrityError):
                await session.rollback()
                return "conflict"

    results = await asyncio.gather(schedule(), schedule())
    assert sorted(results) == ["conflict", "scheduled"]
    async with session_factory() as session:
        state = (
            await session.execute(
                text(
                    "SELECT status, version FROM customers.registration_records "
                    "WHERE booking_id = :id"
                ),
                {"id": booking_id},
            )
        ).one()
        assert tuple(state) == ("scheduled", 2)
        assert await _audit_count(session) == 1


async def test_possession_refuses_cross_project_final_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = AllowAllIdentity()
    documents = DocumentsService(identity)
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        other_actor, _, _, other_project = await _seed_customer_plan(session)
        evidence_id = await _seed_document(session, actor_id=other_actor, project_id=other_project)
        await session.execute(
            text("UPDATE customers.bookings SET status = 'registered' WHERE id = :id"),
            {"id": booking_id},
        )
        await session.commit()

        service = _service(identity, documents)
        await service.transition_possession(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=PossessionTransition("snag_review"),
        )
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="in project"):
            await service.transition_possession(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                data=PossessionTransition("handed_over", date(2026, 8, 24), evidence_id),
            )
        await session.rollback()
        state = (
            await session.execute(
                text(
                    "SELECT status, version FROM customers.possession_records "
                    "WHERE booking_id = :id"
                ),
                {"id": booking_id},
            )
        ).one()
        assert tuple(state) == ("snag_review", 2)


async def test_registration_and_possession_accept_valid_controlled_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = AllowAllIdentity()
    documents = DocumentsService(identity)
    async with session_factory() as session:
        actor_id, booking_id, _, project_id = await _seed_customer_plan(session)
        evidence_id = await _seed_document(session, actor_id=actor_id, project_id=project_id)
        await session.commit()
        service = _service(identity, documents)

        await service.transition_registration(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=RegistrationTransition("scheduled"),
        )
        registered = await service.transition_registration(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=RegistrationTransition("registered", date(2026, 8, 24), evidence_id),
        )
        await service.transition_possession(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=PossessionTransition("snag_review"),
        )
        possessed = await service.transition_possession(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=PossessionTransition("handed_over", date(2026, 8, 25), evidence_id),
        )
        await session.commit()

        assert registered.status == "registered"
        assert possessed.status == "handed_over"
        booking_state = (
            await session.execute(
                text("SELECT status, version FROM customers.bookings WHERE id = :id"),
                {"id": booking_id},
            )
        ).one()
        assert tuple(booking_state) == ("possessed", 3)


async def test_registration_refuses_draft_final_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = AllowAllIdentity()
    documents = DocumentsService(identity)
    async with session_factory() as session:
        actor_id, booking_id, _, project_id = await _seed_customer_plan(session)
        evidence_id = await _seed_document(
            session, actor_id=actor_id, project_id=project_id, status="draft"
        )
        await session.commit()
        service = _service(identity, documents)
        await service.transition_registration(
            session,
            actor_user_id=actor_id,
            booking_id=booking_id,
            data=RegistrationTransition("scheduled"),
        )
        await session.commit()

        with pytest.raises(CustomerLifecycleConflictError, match="accepted revision state"):
            await service.transition_registration(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                data=RegistrationTransition("registered", date(2026, 8, 24), evidence_id),
            )
        await session.rollback()
        state = (
            await session.execute(
                text(
                    "SELECT status, version FROM customers.registration_records "
                    "WHERE booking_id = :id"
                ),
                {"id": booking_id},
            )
        ).one()
        assert tuple(state) == ("scheduled", 2)


async def test_collection_and_audit_roll_back_together_on_audit_failure(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(service_module, "record_event", fail_audit)
    async with session_factory() as session:
        actor_id, booking_id, _, _ = await _seed_customer_plan(session)
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            await _service(AllowAllIdentity()).record_collection(
                session,
                actor_user_id=actor_id,
                booking_id=booking_id,
                data=CollectionCreate(Decimal("10"), date(2026, 8, 24)),
            )
        await session.rollback()
        count = await session.scalar(
            text("SELECT COUNT(*) FROM customers.collections WHERE booking_id = :id"),
            {"id": booking_id},
        )
        assert count == 0
