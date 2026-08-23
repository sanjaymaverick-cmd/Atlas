"""Phase 6 cumulative material issuance integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.project_controls.contracts import ProjectControlsConflictError
from atlas.modules.project_controls.schemas import IssuanceCreate
from atlas.modules.project_controls.service import ProjectControlsService
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


class ReceiptLockProbeIdentity(AllowAllIdentity):
    def __init__(self) -> None:
        self.calls = 0
        self.first_has_lock = asyncio.Event()
        self.release_first = asyncio.Event()

    async def check_scoped_role(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.calls += 1
        if self.calls == 1:
            self.first_has_lock.set()
            await self.release_first.wait()
        return True


@pytest.fixture
async def session_factory(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_receipt(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    material_id, receipt_id = uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Inventory Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"inventory-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Inventory Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Inventory Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Inventory Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-INV-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO inventory.materials "
            "(id, name, unit_of_measure, category, created_by, updated_by, version) "
            "VALUES (:id, :name, 'kg', 'synthetic', :actor_id, :actor_id, 1)"
        ),
        {"id": material_id, "name": f"Synthetic Material {material_id}", "actor_id": actor_id},
    )
    await session.execute(
        text(
            "INSERT INTO inventory.material_receipts "
            "(id, project_id, material_id, quantity_received, received_date, status, "
            "created_by, updated_by, version) VALUES "
            "(:id, :project_id, :material_id, 100, :received_date, 'received', "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": receipt_id,
            "project_id": project_id,
            "material_id": material_id,
            "received_date": date(2026, 8, 23),
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return actor_id, receipt_id


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


async def _issue(
    session: AsyncSession,
    identity: AllowAllIdentity,
    *,
    actor_id: UUID,
    receipt_id: UUID,
    quantity: Decimal,
) -> None:
    await ProjectControlsService(identity).issue_material(
        session,
        actor_user_id=actor_id,
        receipt_id=receipt_id,
        data=IssuanceCreate(
            quantity_issued=quantity,
            issued_date=date(2026, 8, 23),
            issued_to="Synthetic Site",
        ),
    )


async def test_material_issuance_refuses_cumulative_overdraw(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, receipt_id = await _seed_receipt(session)
        await _issue(
            session,
            AllowAllIdentity(),
            actor_id=actor_id,
            receipt_id=receipt_id,
            quantity=Decimal("80"),
        )
        await session.commit()

        with pytest.raises(ProjectControlsConflictError, match="exceeds"):
            await _issue(
                session,
                AllowAllIdentity(),
                actor_id=actor_id,
                receipt_id=receipt_id,
                quantity=Decimal("30"),
            )
        await session.rollback()

        total = await session.scalar(
            text(
                "SELECT COALESCE(SUM(quantity_issued), 0) "
                "FROM inventory.material_issuances WHERE material_receipt_id = :id"
            ),
            {"id": receipt_id},
        )
        assert Decimal(total or 0) == Decimal("80")
        assert len(await _audit_chain(session)) == 1


async def test_concurrent_issuance_blocks_on_receipt_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, receipt_id = await _seed_receipt(seed)
    identity = ReceiptLockProbeIdentity()

    async def issue(quantity: Decimal) -> str:
        async with session_factory() as session:
            try:
                await _issue(
                    session,
                    identity,
                    actor_id=actor_id,
                    receipt_id=receipt_id,
                    quantity=quantity,
                )
                await session.commit()
                return "issued"
            except ProjectControlsConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(issue(Decimal("60")))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(issue(Decimal("60")))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["conflict", "issued"]

    async with session_factory() as session:
        total = await session.scalar(
            text(
                "SELECT COALESCE(SUM(quantity_issued), 0) "
                "FROM inventory.material_issuances WHERE material_receipt_id = :id"
            ),
            {"id": receipt_id},
        )
        assert Decimal(total or 0) == Decimal("60")
        assert len(await _audit_chain(session)) == 1


async def test_valid_issuance_commits_one_valid_audit_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, receipt_id = await _seed_receipt(session)
        await _issue(
            session,
            AllowAllIdentity(),
            actor_id=actor_id,
            receipt_id=receipt_id,
            quantity=Decimal("25"),
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert [(event.entity_schema, event.entity_table, event.action) for event in chain] == [
            ("inventory", "material_issuances", "create")
        ]
        assert verify_chain(chain) == 1
