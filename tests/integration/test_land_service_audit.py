"""Phase 3 land mutations and audit events share one database transaction."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.land.schemas import LandParcelCreate
from atlas.modules.land.service import LandService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = [pytest.mark.integration]


class AllowAllIdentity:
    """Identity contract double restricted to the role check Land publishes."""

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


async def _seed_scope(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id = uuid4()
    group_id = uuid4()
    entity_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users "
            "(id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Synthetic Land Actor', :email, false, 'active', 1)"
        ),
        {"id": actor_id, "email": f"land-actor-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Land Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Land Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.commit()
    return actor_id, entity_id


async def _audit_chain(session: AsyncSession) -> list[AuditRecord]:
    rows = (
        await session.execute(
            text(
                "SELECT seq, entity_schema, entity_table, entity_id, action, "
                "after_state::text, occurred_at, prev_hash, record_hash "
                "FROM audit.audit_events ORDER BY seq"
            )
        )
    ).all()
    return [AuditRecord(*row) for row in rows]


async def test_land_create_commits_with_one_valid_audit_event(
    async_session: AsyncSession,
) -> None:
    actor_id, entity_id = await _seed_scope(async_session)
    service = LandService(AllowAllIdentity())

    created = await service.create_parcel(
        async_session,
        actor_user_id=actor_id,
        data=LandParcelCreate(
            legal_entity_id=entity_id,
            project_id=None,
            survey_number="SYN-LAND-001",
            area_sqft=None,
            location="Synthetic District",
        ),
    )
    await async_session.commit()

    persisted_id = (
        await async_session.execute(
            text("SELECT id FROM land.land_parcels WHERE id = :id"),
            {"id": created.id},
        )
    ).scalar_one()
    chain = await _audit_chain(async_session)

    assert persisted_id == created.id
    assert [(event.entity_schema, event.entity_table, event.action) for event in chain] == [
        ("land", "land_parcels", "create")
    ]
    assert chain[0].entity_id == created.id
    assert verify_chain(chain) == 1


async def test_land_create_rollback_removes_mutation_and_audit_event(
    async_session: AsyncSession,
) -> None:
    actor_id, entity_id = await _seed_scope(async_session)
    service = LandService(AllowAllIdentity())

    created = await service.create_parcel(
        async_session,
        actor_user_id=actor_id,
        data=LandParcelCreate(
            legal_entity_id=entity_id,
            project_id=None,
            survey_number="SYN-LAND-ROLLBACK",
            area_sqft=None,
            location=None,
        ),
    )
    await async_session.rollback()

    parcel_count = (
        await async_session.execute(
            text("SELECT count(*) FROM land.land_parcels WHERE id = :id"),
            {"id": created.id},
        )
    ).scalar_one()

    assert parcel_count == 0
    assert await _audit_chain(async_session) == []
