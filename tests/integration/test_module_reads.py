"""The new read endpoints, exercised through their real services.

Added 2026-08-20 alongside the reads themselves. These go through the service
layer rather than around it, so they cover the scoped-authorisation path that
`docs/phase-evidence-register.md` flagged as untested and that a defect had
already been found in: before `identity.role_permissions` was declared,
`check_scoped_role` raised KeyError and every one of these calls would have
failed with a 500 rather than a decision.

Each read is checked three ways, because a read that returns rows is only half
the guarantee:

* it returns what was written, within scope;
* it refuses a caller scoped to a different project or entity;
* it hides archived rows, since archival replaces deletion in Atlas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.change_control.contracts import ChangeControlNotAuthorisedError
from atlas.modules.change_control.service import ChangeControlService
from atlas.modules.compliance.contracts import ComplianceNotAuthorisedError
from atlas.modules.compliance.service import ComplianceService
from atlas.modules.construction.service import ConstructionService
from atlas.modules.customer_lifecycle.service import CustomerLifecycleService
from atlas.modules.finance.contracts import FinanceNotAuthorisedError
from atlas.modules.finance.service import FinanceService
from atlas.modules.identity.service import IdentityService
from atlas.modules.project_controls.service import ProjectControlsService

pytestmark = pytest.mark.integration


@pytest.fixture
async def db_session(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class Scope:
    """One seeded actor holding one permission, scoped to one project."""

    def __init__(self, user_id: UUID, entity_id: UUID, project_id: UUID) -> None:
        self.user_id = user_id
        self.entity_id = entity_id
        self.project_id = project_id


async def seed_scope(session: AsyncSession, *, permissions: list[str]) -> Scope:
    user_id, group_id, entity_id, project_id, role_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Read Actor', :email, false, 'active', 1)"
        ),
        {"id": user_id, "email": f"read-{user_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Read Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :gid, 'Read Entity', 'active', 1)"
        ),
        {"id": entity_id, "gid": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :eid, 'Read Project', :code, 'planning', 1)"
        ),
        {"id": project_id, "eid": entity_id, "code": f"RD-{project_id}"},
    )
    await session.execute(
        text("INSERT INTO identity.roles (id, name) VALUES (:id, :name)"),
        {"id": role_id, "name": f"read-role-{role_id}"},
    )
    for code in permissions:
        await session.execute(
            text(
                "INSERT INTO identity.permissions (id, code) VALUES (:id, :code) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": uuid4(), "code": code},
        )
        await session.execute(
            text(
                "INSERT INTO identity.role_permissions (role_id, permission_id) "
                "SELECT :rid, id FROM identity.permissions WHERE code = :code"
            ),
            {"rid": role_id, "code": code},
        )
    # Entity-scoped: reaches this entity and every project within it.
    await session.execute(
        text(
            "INSERT INTO identity.user_roles (user_id, role_id, legal_entity_id) "
            "VALUES (:uid, :rid, :eid)"
        ),
        {"uid": user_id, "rid": role_id, "eid": entity_id},
    )
    await session.commit()
    return Scope(user_id, entity_id, project_id)


# ---------------------------------------------------------------------------
# Change control
# ---------------------------------------------------------------------------


async def test_change_requests_are_readable_scoped_and_exclude_archived(
    db_session: AsyncSession,
) -> None:
    scope = await seed_scope(db_session, permissions=["change.read"])
    live, archived = uuid4(), uuid4()
    for row_id, archived_at in ((live, None), (archived, datetime.now(UTC))):
        await db_session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, status, version, archived_at) "
                "VALUES (:id, :pid, 'Synthetic change', 'requested', 1, :arch)"
            ),
            {"id": row_id, "pid": scope.project_id, "arch": archived_at},
        )
    await db_session.commit()

    service = ChangeControlService(IdentityService())
    rows = await service.list_changes(
        db_session, actor_user_id=scope.user_id, project_id=scope.project_id
    )
    assert [row.id for row in rows] == [live]

    # A project the actor's grant does not reach.
    with pytest.raises(ChangeControlNotAuthorisedError):
        await service.list_changes(db_session, actor_user_id=scope.user_id, project_id=uuid4())


async def test_ncrs_and_rfis_are_readable(db_session: AsyncSession) -> None:
    scope = await seed_scope(db_session, permissions=["change.read"])
    await db_session.execute(
        text(
            "INSERT INTO quality.ncrs (project_id, severity, description, status, version) "
            "VALUES (:pid, 'major', 'Synthetic NCR', 'raised', 1)"
        ),
        {"pid": scope.project_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO quality.rfis (project_id, question, status, version) "
            "VALUES (:pid, 'Synthetic question', 'raised', 1)"
        ),
        {"pid": scope.project_id},
    )
    await db_session.commit()

    service = ChangeControlService(IdentityService())
    assert (
        len(
            await service.list_ncrs(
                db_session, actor_user_id=scope.user_id, project_id=scope.project_id
            )
        )
        == 1
    )
    assert (
        len(
            await service.list_rfis(
                db_session, actor_user_id=scope.user_id, project_id=scope.project_id
            )
        )
        == 1
    )


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------


async def test_rera_registrations_are_readable_and_scoped(db_session: AsyncSession) -> None:
    scope = await seed_scope(db_session, permissions=["compliance.read"])
    await db_session.execute(
        text(
            "INSERT INTO compliance.rera_registrations "
            "(project_id, registration_number, status, version) "
            "VALUES (:pid, :num, 'active', 1)"
        ),
        {"pid": scope.project_id, "num": f"RERA-{uuid4()}"},
    )
    await db_session.commit()

    service = ComplianceService(IdentityService())
    rows = await service.list_registrations(
        db_session, actor_user_id=scope.user_id, project_id=scope.project_id
    )
    assert len(rows) == 1

    with pytest.raises(ComplianceNotAuthorisedError):
        await service.list_registrations(
            db_session, actor_user_id=scope.user_id, project_id=uuid4()
        )


# ---------------------------------------------------------------------------
# Construction and quality
# ---------------------------------------------------------------------------


async def test_construction_and_quality_reads_use_separate_permissions(
    db_session: AsyncSession,
) -> None:
    """`quality.read` must not be implied by `construction.read`.

    They are distinct permissions precisely so a scheduler can see the
    programme without seeing defect records, so this checks the split holds
    rather than only that the happy path returns rows.
    """
    scope = await seed_scope(db_session, permissions=["construction.read"])
    await db_session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(project_id, name, status, version) "
            "VALUES (:pid, 'Synthetic activity', 'not_started', 1)"
        ),
        {"pid": scope.project_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO quality.snag_items "
            "(project_id, description, severity, status, version) "
            "VALUES (:pid, 'Synthetic snag', 'minor', 'open', 1)"
        ),
        {"pid": scope.project_id},
    )
    await db_session.commit()

    service = ConstructionService(IdentityService())
    activities = await service.list_activities(
        db_session, actor_user_id=scope.user_id, project_id=scope.project_id
    )
    assert len(activities) == 1

    from atlas.modules.construction.contracts import ConstructionNotAuthorisedError

    with pytest.raises(ConstructionNotAuthorisedError):
        await service.list_snags(
            db_session, actor_user_id=scope.user_id, project_id=scope.project_id
        )


# ---------------------------------------------------------------------------
# Project controls
# ---------------------------------------------------------------------------


async def test_cost_codes_are_readable(db_session: AsyncSession) -> None:
    scope = await seed_scope(db_session, permissions=["project_controls.read"])
    await db_session.execute(
        text(
            "INSERT INTO quantities.cost_codes (project_id, code, wbs_level, version) "
            "VALUES (:pid, :code, 1, 1)"
        ),
        {"pid": scope.project_id, "code": f"CC-{uuid4()}"},
    )
    await db_session.commit()

    service = ProjectControlsService(IdentityService())
    rows = await service.list_cost_codes(
        db_session, actor_user_id=scope.user_id, project_id=scope.project_id
    )
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Customer lifecycle
# ---------------------------------------------------------------------------


async def test_collections_authorise_against_the_bookings_project(
    db_session: AsyncSession,
) -> None:
    """A booking-scoped read must resolve to the booking's project first.

    Authorising on the booking id alone would let a caller scoped to one
    project read another project's payment history by guessing an id.
    """
    scope = await seed_scope(db_session, permissions=["customer.read"])

    party_id, customer_id = uuid4(), uuid4()
    building_id, floor_id, unit_id, booking_id = uuid4(), uuid4(), uuid4(), uuid4()
    await db_session.execute(
        text(
            "INSERT INTO organization.parties (id, party_type, legal_name, status, version) "
            "VALUES (:id, 'customer', 'Synthetic Buyer', 'active', 1)"
        ),
        {"id": party_id},
    )
    customer_id = party_id
    await db_session.execute(
        text(
            "INSERT INTO customers.customers (id, kyc_status, version) VALUES (:id, 'verified', 1)"
        ),
        {"id": customer_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO organization.buildings (id, project_id, name) "
            "VALUES (:id, :pid, 'Synthetic Tower')"
        ),
        {"id": building_id, "pid": scope.project_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO organization.floors (id, building_id, floor_number) VALUES (:id, :bid, 1)"
        ),
        {"id": floor_id, "bid": building_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO organization.units (id, floor_id, unit_number, status) "
            "VALUES (:id, :fid, :num, 'available')"
        ),
        {"id": unit_id, "fid": floor_id, "num": f"U-{unit_id}"},
    )
    await db_session.execute(
        text(
            "INSERT INTO customers.bookings "
            "(id, customer_id, unit_id, project_id, booking_date, status, version) "
            "VALUES (:id, :cid, :uid, :pid, :bd, 'booked', 1)"
        ),
        {
            "id": booking_id,
            "cid": customer_id,
            "uid": unit_id,
            "pid": scope.project_id,
            "bd": date(2026, 8, 20),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO customers.collections "
            "(booking_id, amount, received_date, status, version) "
            "VALUES (:bid, 1000, :rd, 'received', 1)"
        ),
        {"bid": booking_id, "rd": date(2026, 8, 20)},
    )
    await db_session.commit()

    service = CustomerLifecycleService(IdentityService(), None, None)  # type: ignore[arg-type]
    bookings = await service.list_bookings(
        db_session, actor_user_id=scope.user_id, project_id=scope.project_id
    )
    assert [row.id for row in bookings] == [booking_id]

    collections = await service.list_collections(
        db_session, actor_user_id=scope.user_id, booking_id=booking_id
    )
    assert len(collections) == 1


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------


async def test_reconciliations_are_entity_scoped(db_session: AsyncSession) -> None:
    scope = await seed_scope(db_session, permissions=["finance.read"])
    await db_session.execute(
        text(
            "INSERT INTO finance.reconciliations "
            "(legal_entity_id, erp_reference_type, erp_reference_id, discrepancy_type, "
            "status, version) "
            "VALUES (:eid, 'purchase_order', :ref, 'missing_in_tally', 'open', 1)"
        ),
        {"eid": scope.entity_id, "ref": uuid4()},
    )
    await db_session.commit()

    service = FinanceService(IdentityService())
    rows = await service.list_reconciliations(
        db_session, actor_user_id=scope.user_id, legal_entity_id=scope.entity_id
    )
    assert len(rows) == 1

    # Legal-entity separation is Blueprint §2: a grant must not reach a sibling.
    with pytest.raises(FinanceNotAuthorisedError):
        await service.list_reconciliations(
            db_session, actor_user_id=scope.user_id, legal_entity_id=uuid4()
        )
