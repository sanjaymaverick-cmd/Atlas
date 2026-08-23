"""Phase 4 purchase-order gates and audit writes against real PostgreSQL."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.commercial.contracts import CommercialConflictError
from atlas.modules.commercial.service import CommercialService
from atlas.platform.audit.chain import AuditRecord, verify_chain

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


async def _seed_approved_order(
    session: AsyncSession, *, onboarding_status: str
) -> tuple[UUID, UUID]:
    actor_id = uuid4()
    group_id = uuid4()
    entity_id = uuid4()
    project_id = uuid4()
    vendor_id = uuid4()
    onboarding_id = uuid4()
    order_id = uuid4()

    await session.execute(
        text(
            "INSERT INTO identity.users "
            "(id, full_name, email, is_owner, status, version) "
            "VALUES (:id, 'Synthetic Procurement Actor', :email, false, 'active', 1)"
        ),
        {"id": actor_id, "email": f"procurement-actor-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Procurement Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Procurement Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Procurement Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-PO-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.parties "
            "(id, party_type, legal_name, status, version) "
            "VALUES (:id, 'vendor', 'Synthetic Procurement Vendor', 'active', 1)"
        ),
        {"id": vendor_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.vendors (id, category, status) "
            "VALUES (:id, 'synthetic-materials', 'active')"
        ),
        {"id": vendor_id},
    )
    await session.execute(
        text(
            "INSERT INTO vendor_onboarding.vendor_onboardings "
            "(id, vendor_id, status, created_by, updated_by, version) "
            "VALUES (:id, :vendor_id, :status, :actor_id, :actor_id, 5)"
        ),
        {
            "id": onboarding_id,
            "vendor_id": vendor_id,
            "status": onboarding_status,
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO procurement.purchase_orders "
            "(id, project_id, vendor_id, total_amount, status, created_by, updated_by, version) "
            "VALUES (:id, :project_id, :vendor_id, :amount, 'approved', "
            ":actor_id, :actor_id, 3)"
        ),
        {
            "id": order_id,
            "project_id": project_id,
            "vendor_id": vendor_id,
            "amount": Decimal("1250.00"),
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return actor_id, order_id


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


async def test_purchase_order_issue_refuses_approved_but_not_active_onboarding(
    async_session: AsyncSession,
) -> None:
    actor_id, order_id = await _seed_approved_order(async_session, onboarding_status="approved")

    with pytest.raises(CommercialConflictError, match="onboarding is active"):
        await CommercialService(AllowAllIdentity()).transition_purchase_order(
            async_session,
            actor_user_id=actor_id,
            purchase_order_id=order_id,
            target_status="issued",
        )
    await async_session.rollback()

    status = (
        await async_session.execute(
            text("SELECT status FROM procurement.purchase_orders WHERE id = :id"),
            {"id": order_id},
        )
    ).scalar_one()
    assert status == "approved"
    assert await _audit_chain(async_session) == []


async def test_purchase_order_issue_commits_with_one_valid_audit_event(
    async_session: AsyncSession,
) -> None:
    actor_id, order_id = await _seed_approved_order(async_session, onboarding_status="active")

    issued = await CommercialService(AllowAllIdentity()).transition_purchase_order(
        async_session,
        actor_user_id=actor_id,
        purchase_order_id=order_id,
        target_status="issued",
    )
    await async_session.commit()

    chain = await _audit_chain(async_session)
    assert issued.status == "issued" and issued.version == 4 and issued.issued_at is not None
    assert [(event.entity_schema, event.entity_table, event.action) for event in chain] == [
        ("procurement", "purchase_orders", "transition")
    ]
    assert chain[0].entity_id == order_id
    assert verify_chain(chain) == 1


async def test_purchase_order_issue_rollback_removes_state_change_and_event(
    async_session: AsyncSession,
) -> None:
    actor_id, order_id = await _seed_approved_order(async_session, onboarding_status="active")

    await CommercialService(AllowAllIdentity()).transition_purchase_order(
        async_session,
        actor_user_id=actor_id,
        purchase_order_id=order_id,
        target_status="issued",
    )
    await async_session.rollback()

    row = (
        await async_session.execute(
            text(
                "SELECT status, issued_at, version FROM procurement.purchase_orders WHERE id = :id"
            ),
            {"id": order_id},
        )
    ).one()
    assert tuple(row) == ("approved", None, 3)
    assert await _audit_chain(async_session) == []
