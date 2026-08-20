"""Seed a synthetic tenant and mint a session token, for local development.

Atlas has no password login. Authentication is a WebAuthn passkey bound to an
owner-approved device, and a passkey cannot be created without a real
authenticator and a human gesture — so there is no "demo login" to hand out
and no way to script one. This exists instead: it writes the rows a completed
ceremony would have written, and prints the resulting opaque session token so
the web client can be exercised.

**This bypasses authentication.** It is a development affordance and nothing
else. Guarded the same way the destructive baseline downgrade is, so running it
has to be deliberate:

    ATLAS_ALLOW_DEV_SEED=1 \\
    ATLAS_DATABASE_URL='postgresql+asyncpg://atlas@/atlas?host=/tmp&port=55432' \\
    python scripts/dev_seed.py

Everything it writes is synthetic. Never point it at a database holding real
business data — see docs/production-readiness-todo.md, where the question of
whether this should ship at all is recorded for owner review.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from atlas.modules.identity.sessions import issue_token

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_HOURS = 8


def discover_permissions() -> list[str]:
    """Every permission code the service layer checks.

    Scanned rather than listed so the seeded role keeps working as modules add
    permissions. A real role would never hold all of them at once; this one
    does precisely because it is not a real role.
    """
    codes: set[str] = set()
    for path in (REPO_ROOT / "atlas" / "modules").glob("*/service.py"):
        codes.update(re.findall(r'"([a-z_]+\.[a-z_.]+)"', path.read_text(encoding="utf-8")))
    return sorted(codes)


async def seed(session: AsyncSession) -> dict[str, str]:
    ids = {name: uuid4() for name in ("user", "group", "entity", "role", "device")}
    token, token_hash = issue_token()
    suffix = str(ids["entity"])[:4].upper()

    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Dev Owner (synthetic)', :email, true, 'active', 1)"
        ),
        {"id": ids["user"], "email": f"dev-{ids['user']}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Dev Group (synthetic)', 'active', 1)"
        ),
        {"id": ids["group"]},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :gid, 'Dev Holdings (synthetic)', 'active', 1)"
        ),
        {"id": ids["entity"], "gid": ids["group"]},
    )

    await session.execute(
        text("INSERT INTO identity.roles (id, name, description) VALUES (:id, :n, :d)"),
        {"id": ids["role"], "n": f"dev-all-{ids['role']}", "d": "Synthetic development role"},
    )
    for code in discover_permissions():
        await session.execute(
            text(
                "INSERT INTO identity.permissions (id, code, description) "
                "VALUES (:id, :code, 'development seed') ON CONFLICT (code) DO NOTHING"
            ),
            {"id": uuid4(), "code": code},
        )
        await session.execute(
            text(
                "INSERT INTO identity.role_permissions (role_id, permission_id) "
                "SELECT :rid, id FROM identity.permissions WHERE code = :code "
                "ON CONFLICT DO NOTHING"
            ),
            {"rid": ids["role"], "code": code},
        )

    # Two grants. The entity-scoped one covers the entity and its projects; the
    # global one is what estate-wide reads such as the material master need,
    # and scoping deliberately refuses those to an entity-scoped grant alone.
    for scope in ({"eid": ids["entity"]}, {"eid": None}):
        await session.execute(
            text(
                "INSERT INTO identity.user_roles (user_id, role_id, legal_entity_id) "
                "VALUES (:uid, :rid, :eid)"
            ),
            {"uid": ids["user"], "rid": ids["role"], **scope},
        )

    await session.execute(
        text(
            "INSERT INTO identity.devices "
            "(id, user_id, passkey_credential_id, public_key, trust_level, status) "
            "VALUES (:id, :uid, :cred, 'synthetic-dev-key', 'elevated', 'active')"
        ),
        {"id": ids["device"], "uid": ids["user"], "cred": f"dev-{ids['device']}"},
    )
    await session.execute(
        text(
            "INSERT INTO identity.sessions "
            "(user_id, device_id, session_token_hash, expires_at) "
            "VALUES (:uid, :did, :hash, :exp)"
        ),
        {
            "uid": ids["user"],
            "did": ids["device"],
            "hash": token_hash,
            "exp": datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
        },
    )

    # Project codes are globally unique, not per entity, so they carry a suffix
    # to keep repeated runs from colliding.
    projects: dict[str, UUID] = {}
    for name, code, city, status in (
        ("Riverside Residences", f"RIV-{suffix}", "Pune", "active"),
        ("Harbour Point Commercial", f"HPC-{suffix}", "Mumbai", "planning"),
        ("Green Meadows Phase II", f"GMP-{suffix}", "Nashik", "on_hold"),
    ):
        project_id = uuid4()
        projects[code] = project_id
        await session.execute(
            text(
                "INSERT INTO organization.projects "
                "(id, legal_entity_id, name, code, city, status, version, created_by) "
                "VALUES (:id, :eid, :n, :c, :city, :s, 1, :uid)"
            ),
            {
                "id": project_id,
                "eid": ids["entity"],
                "n": name,
                "c": code,
                "city": city,
                "s": status,
                "uid": ids["user"],
            },
        )

    await seed_module_records(session, projects[f"RIV-{suffix}"], ids["entity"], suffix)
    await session.commit()

    return {
        "user_id": str(ids["user"]),
        "legal_entity_id": str(ids["entity"]),
        "session_token": token,
    }


async def seed_module_records(
    session: AsyncSession, project_id: UUID, entity_id: UUID, suffix: str
) -> None:
    """A few rows in each module, so the registers are not empty on first look."""
    await session.execute(
        text(
            "INSERT INTO construction.change_requests "
            "(project_id, description, status, version) "
            "VALUES (:pid, 'Revised podium slab thickness', 'feasibility_review', 1)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO quality.rfis (project_id, question, status, version) "
            "VALUES (:pid, 'Confirm rebar spacing at grid C4', 'raised', 1)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO quality.ncrs (project_id, severity, description, status, version) "
            "VALUES (:pid, 'major', 'Honeycombing to column C4', 'raised', 1)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO quality.snag_items "
            "(project_id, description, severity, status, version) "
            "VALUES (:pid, 'Door frame out of plumb, unit 402', 'minor', 'open', 1)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO compliance.rera_registrations "
            "(project_id, registration_number, status, version) "
            "VALUES (:pid, :num, 'active', 1)"
        ),
        {"pid": project_id, "num": f"P-RERA-{suffix}"},
    )
    await session.execute(
        text(
            "INSERT INTO compliance.compliance_obligations "
            "(project_id, obligation_type, authority, due_date, status, version) "
            "VALUES (:pid, 'Quarterly RERA return', 'MahaRERA', :due, 'open', 1)"
        ),
        {"pid": project_id, "due": date(2026, 9, 30)},
    )
    await session.execute(
        text(
            "INSERT INTO construction.schedule_activities "
            "(project_id, name, status, version) "
            "VALUES (:pid, 'Podium slab pour', 'in_progress', 1)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO construction.ehs_incidents "
            "(project_id, incident_date, severity, description, status, version) "
            "VALUES (:pid, :d, 'near_miss', 'Scaffold plank displaced', 'open', 1)"
        ),
        {"pid": project_id, "d": date(2026, 8, 12)},
    )
    await session.execute(
        text(
            "INSERT INTO quantities.cost_codes "
            "(project_id, code, description, wbs_level, version) "
            "VALUES (:pid, :c, 'Substructure concrete', 1, 1)"
        ),
        {"pid": project_id, "c": f"CC-{suffix}-01"},
    )
    await session.execute(
        text(
            "INSERT INTO finance.reconciliations "
            "(legal_entity_id, erp_reference_type, erp_reference_id, discrepancy_type, "
            "status, version) "
            "VALUES (:eid, 'purchase_order', :ref, 'missing_in_tally', 'open', 1)"
        ),
        {"eid": entity_id, "ref": uuid4()},
    )


async def main() -> int:
    if os.environ.get("ATLAS_ALLOW_DEV_SEED") != "1":
        print(
            "Refusing to run. This writes synthetic users, grants every permission "
            "to one role and mints a session token that bypasses the passkey "
            "ceremony entirely.\n\nSet ATLAS_ALLOW_DEV_SEED=1 if that is genuinely "
            "what you intend, and never against a database holding real data.",
            file=sys.stderr,
        )
        return 2

    url = os.environ.get("ATLAS_DATABASE_URL")
    if not url:
        print("ATLAS_DATABASE_URL is required.", file=sys.stderr)
        return 2

    engine = create_async_engine(url)
    async with AsyncSession(engine) as session:
        result = await seed(session)
    await engine.dispose()

    print("\nSynthetic tenant seeded. All data is fake.\n")
    print(f"  Legal entity ID : {result['legal_entity_id']}")
    print(f"  User ID         : {result['user_id']}")
    print(f"  Session token   : {result['session_token']}")
    print(f"\nToken is valid for {SESSION_HOURS} hours and is revocable server-side.")
    print("Paste it into the web client's sign-in screen under 'Development token'.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
