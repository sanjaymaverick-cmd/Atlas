"""One database-enforced invariant per phase, for Phases 3 through 10.

Written 2026-08-18 to close the gap `docs/phase-evidence-register.md` records:
every pre-existing integration test covered Phase 1 or a two-test slice of
Phase 2, so Phases 3-10 were evidenced only by database-free service tests and
one route-thinness test each. Atlas deliberately puts its integrity in the
database, and a mocked test cannot evidence a constraint that lives in
PostgreSQL — these do.

Each test targets the strongest rule its phase actually enforces in the
database, and each asserts a *violation is rejected* rather than that a happy
path succeeds, because the rejection is the guarantee.

Every test also asserts which constraint rejected it. That is not decoration:
several of these tables carry more than one constraint that a careless fixture
could trip instead — `construction.site_diary_entries` has both a
one-diary-per-day key and the idempotency key tested here — and a test that
merely caught `UniqueViolation` could pass while exercising the wrong rule
entirely. Naming the constraint is what makes these tests evidence.

Deliberately not covered here, because the database does not enforce them:
Phase 4's "a purchase order cannot be issued until the vendor is active" is
application-layer by design — `procurement.purchase_orders` says so in a
comment — and Phase 6's cumulative-stock ceiling is a service-level check.
Those need service-level tests, which the register lists separately.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

pytestmark = pytest.mark.integration


def _seed_entity(db: Any) -> tuple[UUID, UUID]:
    """A user and a legal entity, the root most domain rows hang off."""
    user_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
        "VALUES (%(id)s, 'Synthetic Invariant Actor', %(email)s, false, 'active', 1)",
        {"id": user_id, "email": f"invariant-{user_id}@example.invalid"},
    )
    db.execute(
        "INSERT INTO organization.business_groups (id, name, status, version) "
        "VALUES (%(id)s, 'Synthetic Group', 'active', 1)",
        {"id": group_id},
    )
    db.execute(
        "INSERT INTO organization.legal_entities "
        "(id, business_group_id, name, status, version) "
        "VALUES (%(id)s, %(group_id)s, 'Synthetic Entity', 'active', 1)",
        {"id": entity_id, "group_id": group_id},
    )
    return user_id, entity_id


def _seed_project(db: Any, entity_id: UUID) -> UUID:
    project_id = uuid4()
    db.execute(
        "INSERT INTO organization.projects "
        "(id, legal_entity_id, name, code, status, version) "
        "VALUES (%(id)s, %(entity_id)s, 'Synthetic Project', %(code)s, 'planning', 1)",
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-{project_id}"},
    )
    return project_id


def _seed_unit(db: Any, project_id: UUID) -> UUID:
    building_id, floor_id, unit_id = uuid4(), uuid4(), uuid4()
    db.execute(
        "INSERT INTO organization.buildings (id, project_id, name) "
        "VALUES (%(id)s, %(project_id)s, 'Synthetic Tower')",
        {"id": building_id, "project_id": project_id},
    )
    db.execute(
        "INSERT INTO organization.floors (id, building_id, floor_number) "
        "VALUES (%(id)s, %(building_id)s, 1)",
        {"id": floor_id, "building_id": building_id},
    )
    db.execute(
        "INSERT INTO organization.units (id, floor_id, unit_number, status) "
        "VALUES (%(id)s, %(floor_id)s, %(number)s, 'available')",
        {"id": unit_id, "floor_id": floor_id, "number": f"U-{unit_id}"},
    )
    return unit_id


def _seed_party(db: Any, party_type: str) -> UUID:
    party_id = uuid4()
    db.execute(
        "INSERT INTO organization.parties (id, party_type, legal_name, status, version) "
        "VALUES (%(id)s, %(party_type)s, 'Synthetic Party', 'active', 1)",
        {"id": party_id, "party_type": party_type},
    )
    return party_id


# --------------------------------------------------------------------------
# Phase 3 — land and compliance
# --------------------------------------------------------------------------


def test_phase3_a_rera_number_cannot_be_claimed_by_two_projects(db: Any) -> None:
    """A RERA registration number is a statutory identifier for one project.

    Two projects holding the same number would misrepresent the registration to
    the regulator, so uniqueness is global rather than per-project.
    """
    _, entity_id = _seed_entity(db)
    first_project = _seed_project(db, entity_id)
    second_project = _seed_project(db, entity_id)
    number = f"RERA-{uuid4()}"

    db.execute(
        "INSERT INTO compliance.rera_registrations "
        "(project_id, registration_number, status, version) "
        "VALUES (%(project_id)s, %(number)s, 'active', 1)",
        {"project_id": first_project, "number": number},
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        db.execute(
            "INSERT INTO compliance.rera_registrations "
            "(project_id, registration_number, status, version) "
            "VALUES (%(project_id)s, %(number)s, 'active', 1)",
            {"project_id": second_project, "number": number},
        )
    assert violation.value.diag.constraint_name == "rera_registrations_registration_number_key"


# --------------------------------------------------------------------------
# Phase 4 — commercial and vendor onboarding
# --------------------------------------------------------------------------


def test_phase4_a_vendor_cannot_have_two_onboarding_records(db: Any) -> None:
    """One onboarding record per vendor, so approval has a single history.

    Two parallel onboardings could each reach 'approved' by a different route,
    which would make "is this vendor approved?" unanswerable from the data.
    """
    _seed_entity(db)
    vendor_id = _seed_party(db, "vendor")
    db.execute(
        "INSERT INTO organization.vendors (id, status) VALUES (%(id)s, 'invited')",
        {"id": vendor_id},
    )

    db.execute(
        "INSERT INTO vendor_onboarding.vendor_onboardings (vendor_id, status, version) "
        "VALUES (%(vendor_id)s, 'invited', 1)",
        {"vendor_id": vendor_id},
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        db.execute(
            "INSERT INTO vendor_onboarding.vendor_onboardings "
            "(vendor_id, status, version) VALUES (%(vendor_id)s, 'kyc_submitted', 1)",
            {"vendor_id": vendor_id},
        )
    assert violation.value.diag.constraint_name == "vendor_onboardings_vendor_id_key"


# --------------------------------------------------------------------------
# Phase 5 — construction and site diaries
# --------------------------------------------------------------------------


def test_phase5_a_replayed_site_diary_entry_is_rejected(db: Any) -> None:
    """Offline idempotency: a device replaying an entry must not duplicate it.

    Site diaries are captured offline and synced later, so the same entry can
    arrive twice. `client_record_id` is the device's own idempotency key. The
    replay deliberately uses a *different* `entry_date`, so the separate
    one-diary-per-day key cannot be what rejects it — and the asserted
    constraint name proves which of the two actually fired.
    """
    _, entity_id = _seed_entity(db)
    project_id = _seed_project(db, entity_id)
    client_record_id = uuid4()

    db.execute(
        "INSERT INTO construction.site_diary_entries "
        "(project_id, entry_date, client_record_id, status, version) "
        "VALUES (%(project_id)s, %(entry_date)s, %(client_record_id)s, 'submitted', 1)",
        {
            "project_id": project_id,
            "entry_date": date(2026, 8, 17),
            "client_record_id": client_record_id,
        },
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        db.execute(
            "INSERT INTO construction.site_diary_entries "
            "(project_id, entry_date, client_record_id, status, version) "
            "VALUES (%(project_id)s, %(entry_date)s, %(client_record_id)s, "
            "'submitted', 1)",
            {
                "project_id": project_id,
                "entry_date": date(2026, 8, 18),
                "client_record_id": client_record_id,
            },
        )
    assert (
        violation.value.diag.constraint_name == "site_diary_entries_project_id_client_record_id_key"
    )


# --------------------------------------------------------------------------
# Phase 6 — project controls and material traceability
# --------------------------------------------------------------------------


def test_phase6_material_cannot_be_received_against_another_projects_po(
    db: Any,
) -> None:
    """Cost cannot leak between projects through a mis-scoped receipt.

    The composite `(purchase_order_id, project_id)` foreign key makes the
    project part of the reference itself, so a receipt booked to one project
    cannot cite a purchase order belonging to another.
    """
    _, entity_id = _seed_entity(db)
    po_project = _seed_project(db, entity_id)
    other_project = _seed_project(db, entity_id)

    vendor_id = _seed_party(db, "vendor")
    db.execute(
        "INSERT INTO organization.vendors (id, status) VALUES (%(id)s, 'active')",
        {"id": vendor_id},
    )
    purchase_order_id, material_id = uuid4(), uuid4()
    db.execute(
        "INSERT INTO procurement.purchase_orders "
        "(id, project_id, vendor_id, total_amount, status, version) "
        "VALUES (%(id)s, %(project_id)s, %(vendor_id)s, 1000, 'issued', 1)",
        {"id": purchase_order_id, "project_id": po_project, "vendor_id": vendor_id},
    )
    db.execute(
        "INSERT INTO inventory.materials (id, name, unit_of_measure, version) "
        "VALUES (%(id)s, %(name)s, 'bag', 1)",
        {"id": material_id, "name": f"Synthetic Cement {material_id}"},
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
        db.execute(
            "INSERT INTO inventory.material_receipts "
            "(project_id, purchase_order_id, material_id, quantity_received, "
            "received_date, status, version) "
            "VALUES (%(project_id)s, %(po_id)s, %(material_id)s, 10, "
            "%(received_date)s, 'received', 1)",
            {
                "project_id": other_project,
                "po_id": purchase_order_id,
                "material_id": material_id,
                "received_date": date(2026, 8, 18),
            },
        )
    assert (
        violation.value.diag.constraint_name
        == "material_receipts_purchase_order_id_project_id_fkey"
    )


# --------------------------------------------------------------------------
# Phase 7 — change control and quality
# --------------------------------------------------------------------------


def test_phase7_an_ncr_cannot_cite_another_projects_inspection(db: Any) -> None:
    """A non-conformance must be traceable to an inspection on its own project.

    Enforced by the composite `(inspection_id, project_id)` foreign key, so the
    link cannot silently cross a project boundary and attribute a defect to the
    wrong job.
    """
    _, entity_id = _seed_entity(db)
    inspection_project = _seed_project(db, entity_id)
    other_project = _seed_project(db, entity_id)

    inspection_id = uuid4()
    db.execute(
        "INSERT INTO quality.inspections (id, project_id, status, version) "
        "VALUES (%(id)s, %(project_id)s, 'completed', 1)",
        {"id": inspection_id, "project_id": inspection_project},
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
        db.execute(
            "INSERT INTO quality.ncrs "
            "(project_id, inspection_id, severity, description, status, version) "
            "VALUES (%(project_id)s, %(inspection_id)s, 'major', "
            "'Synthetic non-conformance', 'raised', 1)",
            {"project_id": other_project, "inspection_id": inspection_id},
        )
    assert violation.value.diag.constraint_name == "ncrs_inspection_id_project_id_fkey"


# --------------------------------------------------------------------------
# Phase 8 — customer lifecycle
# --------------------------------------------------------------------------


def test_phase8_a_unit_cannot_be_actively_booked_twice(db: Any) -> None:
    """Selling one unit to two customers is the defining Phase 8 failure.

    The guarantee is a *partial* unique index — active bookings only — so this
    also checks the predicate: once the first booking is cancelled the unit
    becomes bookable again. A blanket unique index would pass the first
    assertion and wrongly fail the second.
    """
    _, entity_id = _seed_entity(db)
    project_id = _seed_project(db, entity_id)
    unit_id = _seed_unit(db, project_id)

    customer_id = _seed_party(db, "customer")
    db.execute(
        "INSERT INTO customers.customers (id, kyc_status, version) VALUES (%(id)s, 'verified', 1)",
        {"id": customer_id},
    )

    first_booking = uuid4()
    db.execute(
        "INSERT INTO customers.bookings "
        "(id, customer_id, unit_id, project_id, booking_date, status, version) "
        "VALUES (%(id)s, %(customer_id)s, %(unit_id)s, %(project_id)s, "
        "%(booking_date)s, 'booked', 1)",
        {
            "id": first_booking,
            "customer_id": customer_id,
            "unit_id": unit_id,
            "project_id": project_id,
            "booking_date": date(2026, 8, 18),
        },
    )

    second_booking = {
        "customer_id": customer_id,
        "unit_id": unit_id,
        "project_id": project_id,
        "booking_date": date(2026, 8, 19),
    }
    insert_second = (
        "INSERT INTO customers.bookings "
        "(customer_id, unit_id, project_id, booking_date, status, version) "
        "VALUES (%(customer_id)s, %(unit_id)s, %(project_id)s, "
        "%(booking_date)s, 'booked', 1)"
    )
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        db.execute(insert_second, second_booking)
    assert violation.value.diag.constraint_name == "uq_active_booking_unit"

    # Cancelling the first booking must release the unit, or the index is not
    # actually partial and a cancelled sale would block the unit forever.
    db.execute(
        "UPDATE customers.bookings SET status = 'cancelled' WHERE id = %(id)s",
        {"id": first_booking},
    )
    db.execute(insert_second, second_booking)


# --------------------------------------------------------------------------
# Phase 9 — Tally reconciliation
# --------------------------------------------------------------------------


def test_phase9_the_same_discrepancy_cannot_be_raised_twice(db: Any) -> None:
    """One open case per reconciliation fact, so a discrepancy is not double-counted.

    `uq_reconciliation_fact` folds a NULL voucher to a sentinel UUID, which is
    what makes this hold for the missing-in-Tally case — a plain unique index
    would treat every NULL as distinct and let duplicates through. That NULL
    path is the one exercised here.
    """
    _, entity_id = _seed_entity(db)
    fact = {"entity_id": entity_id, "erp_reference_id": uuid4()}
    statement = (
        "INSERT INTO finance.reconciliations "
        "(legal_entity_id, erp_reference_type, erp_reference_id, tally_voucher_id, "
        "discrepancy_type, status, version) "
        "VALUES (%(entity_id)s, 'purchase_order', %(erp_reference_id)s, NULL, "
        "'missing_in_tally', 'open', 1)"
    )

    db.execute(statement, fact)
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        db.execute(statement, fact)
    assert violation.value.diag.constraint_name == "uq_reconciliation_fact"


# --------------------------------------------------------------------------
# Phase 10 — reporting
# --------------------------------------------------------------------------


def test_phase10_a_project_report_cannot_be_requested_without_a_project(
    db: Any,
) -> None:
    """A project-scoped report with no project would silently widen its scope.

    The entity-level report is the only one allowed to omit a project, so the
    same check is confirmed to permit that case rather than banning NULL outright.
    """
    user_id, entity_id = _seed_entity(db)
    request = (
        "INSERT INTO reporting.report_requests "
        "(legal_entity_id, project_id, report_type, output_format, status, "
        "requested_by, version) "
        "VALUES (%(entity_id)s, NULL, %(report_type)s, 'pdf', 'queued', "
        "%(user_id)s, 1)"
    )
    scope = {"entity_id": entity_id, "user_id": user_id}

    with pytest.raises(psycopg.errors.CheckViolation) as violation:
        db.execute(request, {**scope, "report_type": "ceo_project_summary"})
    assert violation.value.diag.constraint_name == "report_requests_check"

    db.execute(request, {**scope, "report_type": "ceo_entity_summary"})
