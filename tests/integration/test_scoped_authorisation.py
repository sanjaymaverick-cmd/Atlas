"""The real authorisation path, exercised against a real database.

Regression test for a defect that made every scoped endpoint return 500.

``repository.load_grants`` joins roles to permissions through
``identity.role_permissions``, which it reaches via
``Base.metadata.tables["identity.role_permissions"]``. That table exists in
``db/schema.sql`` but had no ORM declaration, so the lookup raised
``KeyError`` and every call to ``IdentityService.check_scoped_role`` failed —
which is to say every authenticated business request in Atlas.

The 325-test suite did not catch it. The unit tests cover ``scoping.py``'s pure
grant-interpretation logic, and the Phase 1 integration tests inject a stub
identity that answers the authorisation question directly, so nothing ever ran
the real ``check_scoped_role`` against PostgreSQL. That is precisely the
service-level gap ``docs/phase-evidence-register.md`` warns about, and this
test closes it for the authorisation path specifically: it goes through
``IdentityService``, not around it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.identity.service import IdentityService

pytestmark = pytest.mark.integration

PERMISSION = "project.read"


@pytest.fixture
async def async_session(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _grant_entity_scoped_permission(session: AsyncSession) -> tuple[UUID, UUID]:
    """Give one user `project.read` on one legal entity, the ordinary case."""
    user_id, group_id, entity_id, role_id = uuid4(), uuid4(), uuid4(), uuid4()

    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Scoped Actor', :email, false, 'active', 1)"
        ),
        {"id": user_id, "email": f"scoped-{user_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Scoped Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :gid, 'Scoped Entity', 'active', 1)"
        ),
        {"id": entity_id, "gid": group_id},
    )
    await session.execute(
        text("INSERT INTO identity.roles (id, name) VALUES (:id, :name)"),
        {"id": role_id, "name": f"scoped-role-{role_id}"},
    )
    # The permission code is shared across the suite, so tolerate it existing.
    await session.execute(
        text(
            "INSERT INTO identity.permissions (id, code) VALUES (:id, :code) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"id": uuid4(), "code": PERMISSION},
    )
    await session.execute(
        text(
            "INSERT INTO identity.role_permissions (role_id, permission_id) "
            "SELECT :role_id, id FROM identity.permissions WHERE code = :code"
        ),
        {"role_id": role_id, "code": PERMISSION},
    )
    await session.execute(
        text(
            "INSERT INTO identity.user_roles (user_id, role_id, legal_entity_id) "
            "VALUES (:user_id, :role_id, :entity_id)"
        ),
        {"user_id": user_id, "role_id": role_id, "entity_id": entity_id},
    )
    await session.commit()
    return user_id, entity_id


async def test_an_entity_scoped_grant_authorises_within_its_entity(
    async_session: AsyncSession,
) -> None:
    """The path that returned 500 for every authenticated request.

    Loading the grant at all is the regression: before the fix this raised
    KeyError inside load_grants rather than returning a decision.
    """
    user_id, entity_id = await _grant_entity_scoped_permission(async_session)

    allowed = await IdentityService().check_scoped_role(
        async_session,
        user_id=user_id,
        permission_code=PERMISSION,
        legal_entity_id=entity_id,
        project_id=None,
    )
    assert allowed is True


async def test_a_grant_does_not_reach_a_sibling_entity(
    async_session: AsyncSession,
) -> None:
    """Scoping narrows and never widens — the point of the whole mechanism.

    Paired with the test above so a fix that simply returned True everywhere
    would fail here. Legal-entity separation is Blueprint §2.
    """
    user_id, _ = await _grant_entity_scoped_permission(async_session)

    allowed = await IdentityService().check_scoped_role(
        async_session,
        user_id=user_id,
        permission_code=PERMISSION,
        legal_entity_id=uuid4(),
        project_id=None,
    )
    assert allowed is False


async def test_an_ungranted_permission_is_refused(async_session: AsyncSession) -> None:
    """Holding one permission must not imply holding another."""
    user_id, entity_id = await _grant_entity_scoped_permission(async_session)

    allowed = await IdentityService().check_scoped_role(
        async_session,
        user_id=user_id,
        permission_code="project.archive",
        legal_entity_id=entity_id,
        project_id=None,
    )
    assert allowed is False
