"""Phase 6 row-locking and transition atomicity against PostgreSQL."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.project_controls.contracts import ProjectControlsConflictError
from atlas.modules.project_controls.service import ProjectControlsService

pytestmark = pytest.mark.integration


class StatusResult(Protocol):
    status: str


class LockProbeIdentity:
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


async def _seed(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    document_id, import_id, quantity_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Transition Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"phase6-transition-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Transition Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Transition Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Transition Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-P6-T-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, version) "
            "VALUES (:id, :project_id, 'bim', 'restricted', 'virus_scanned', 1)"
        ),
        {"id": document_id, "project_id": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO design.bim_imports "
            "(id, project_id, source_file_reference, source_document_id, import_status, "
            "created_by, updated_by, version) "
            "VALUES (:id, :project_id, :source, :document_id, 'received', :actor, :actor, 1)"
        ),
        {
            "id": import_id,
            "project_id": project_id,
            "source": str(document_id),
            "document_id": document_id,
            "actor": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO quantities.quantity_items "
            "(id, project_id, calculated_quantity, tolerance_pct, status, "
            "created_by, updated_by, version) "
            "VALUES (:id, :project_id, 100, 2, 'calculated', :actor, :actor, 1)"
        ),
        {"id": quantity_id, "project_id": project_id, "actor": actor_id},
    )
    await session.commit()
    return actor_id, project_id, import_id, quantity_id


async def _seed_approver(session: AsyncSession) -> UUID:
    approver_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Quantity Approver', :email, 'active', 1)"
        ),
        {"id": approver_id, "email": f"phase6-approver-{approver_id}@example.invalid"},
    )
    await session.commit()
    return approver_id


async def _one_winner(
    session_factory: async_sessionmaker[AsyncSession],
    identity: LockProbeIdentity,
    mutate: Callable[[ProjectControlsService, AsyncSession], Awaitable[StatusResult]],
) -> tuple[StatusResult, Exception]:
    async with session_factory() as first_session, session_factory() as second_session:
        service = ProjectControlsService(identity)

        async def run(session: AsyncSession) -> StatusResult:
            result = await mutate(service, session)
            await session.commit()
            return result

        first = asyncio.create_task(run(first_session))
        await asyncio.wait_for(identity.first_has_lock.wait(), timeout=2)
        second = asyncio.create_task(run(second_session))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), timeout=0.2)
        identity.release_first.set()
        first_result = await asyncio.wait_for(first, timeout=2)
        with pytest.raises(ProjectControlsConflictError) as caught:
            await asyncio.wait_for(second, timeout=2)
        await second_session.rollback()
        return first_result, caught.value


async def test_concurrent_bim_transition_serializes_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed_session:
        actor_id, _, import_id, _ = await _seed(seed_session)
    identity = LockProbeIdentity()

    async def transition(service: ProjectControlsService, session: AsyncSession) -> StatusResult:
        return await service.transition_bim_import(
            session,
            actor_user_id=actor_id,
            import_id=import_id,
            target_status="validating",
        )

    result, error = await _one_winner(session_factory, identity, transition)
    assert result.status == "validating"
    assert "cannot move" in str(error)


async def test_concurrent_quantity_verification_serializes_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed_session:
        actor_id, _, _, quantity_id = await _seed(seed_session)
    identity = LockProbeIdentity()

    async def verify(service: ProjectControlsService, session: AsyncSession) -> StatusResult:
        return await service.verify_quantity(
            session,
            actor_user_id=actor_id,
            quantity_id=quantity_id,
            verified_quantity=Decimal("101"),
        )

    result, error = await _one_winner(session_factory, identity, verify)
    assert result.status == "within_tolerance"
    assert "current state" in str(error)


async def test_concurrent_quantity_approval_serializes_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed_session:
        verifier_id, _, _, quantity_id = await _seed(seed_session)
        approver_id = await _seed_approver(seed_session)
        await seed_session.execute(
            text(
                "UPDATE quantities.quantity_items "
                "SET status = 'within_tolerance', verified_quantity = 101, "
                "updated_by = :verifier "
                "WHERE id = :id"
            ),
            {"id": quantity_id, "verifier": verifier_id},
        )
        await seed_session.commit()
    identity = LockProbeIdentity()

    async def approve(service: ProjectControlsService, session: AsyncSession) -> StatusResult:
        return await service.approve_quantity(
            session,
            actor_user_id=approver_id,
            quantity_id=quantity_id,
            final_quantity=Decimal("101"),
        )

    result, error = await _one_winner(session_factory, identity, approve)
    assert result.status == "approved"
    assert "current state" in str(error)


async def test_bim_transition_rollback_restores_state_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, import_id, _ = await _seed(session)
        audit_count = int(
            await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0
        )
        identity = LockProbeIdentity()
        identity.release_first.set()
        await ProjectControlsService(identity).transition_bim_import(
            session,
            actor_user_id=actor_id,
            import_id=import_id,
            target_status="validating",
        )
        await session.rollback()
        state = (
            await session.execute(
                text("SELECT import_status, version FROM design.bim_imports WHERE id = :id"),
                {"id": import_id},
            )
        ).one()
        assert tuple(state) == ("received", 1)
        assert (
            int(await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0)
            == audit_count
        )


async def test_quantity_verify_and_approve_roll_back_with_their_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        verifier_id, _, _, quantity_id = await _seed(session)
        approver_id = await _seed_approver(session)
        audit_count = int(
            await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0
        )
        identity = LockProbeIdentity()
        identity.release_first.set()
        service = ProjectControlsService(identity)
        await service.verify_quantity(
            session,
            actor_user_id=verifier_id,
            quantity_id=quantity_id,
            verified_quantity=Decimal("101"),
        )
        await session.rollback()
        verified_state = (
            await session.execute(
                text(
                    "SELECT verified_quantity, status, version "
                    "FROM quantities.quantity_items WHERE id = :id"
                ),
                {"id": quantity_id},
            )
        ).one()
        assert tuple(verified_state) == (None, "calculated", 1)
        assert (
            int(await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0)
            == audit_count
        )

        await session.execute(
            text(
                "UPDATE quantities.quantity_items "
                "SET verified_quantity = 101, status = 'within_tolerance', "
                "updated_by = :verifier WHERE id = :id"
            ),
            {"id": quantity_id, "verifier": verifier_id},
        )
        await session.commit()
        await service.approve_quantity(
            session,
            actor_user_id=approver_id,
            quantity_id=quantity_id,
            final_quantity=Decimal("101"),
        )
        await session.rollback()
        approved_state = (
            await session.execute(
                text(
                    "SELECT final_approved_quantity, status, version "
                    "FROM quantities.quantity_items WHERE id = :id"
                ),
                {"id": quantity_id},
            )
        ).one()
        assert tuple(approved_state) == (None, "within_tolerance", 1)
        assert (
            int(await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0)
            == audit_count
        )


async def test_quantity_verifier_cannot_approve_own_measurement(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        verifier_id, _, _, quantity_id = await _seed(session)
        identity = LockProbeIdentity()
        identity.release_first.set()
        service = ProjectControlsService(identity)
        await service.verify_quantity(
            session,
            actor_user_id=verifier_id,
            quantity_id=quantity_id,
            verified_quantity=Decimal("101"),
        )
        await session.commit()
        audit_count = int(
            await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0
        )
        with pytest.raises(ProjectControlsConflictError, match="different attributed verifier"):
            await service.approve_quantity(
                session,
                actor_user_id=verifier_id,
                quantity_id=quantity_id,
                final_quantity=Decimal("101"),
            )
        await session.rollback()
        state = (
            await session.execute(
                text(
                    "SELECT final_approved_quantity, status, version "
                    "FROM quantities.quantity_items WHERE id = :id"
                ),
                {"id": quantity_id},
            )
        ).one()
        assert tuple(state) == (None, "within_tolerance", 2)
        assert (
            int(await session.scalar(text("SELECT count(*) FROM audit.audit_events")) or 0)
            == audit_count
        )
