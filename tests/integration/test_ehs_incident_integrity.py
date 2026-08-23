"""Phase 5 EHS workflow integrity and audit minimization against PostgreSQL."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.service import ConstructionService
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


class IncidentLockProbeIdentity(AllowAllIdentity):
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


async def _seed_incident(
    session: AsyncSession,
    *,
    status: str = "open",
    corrective_action: str | None = None,
) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id, incident_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Safety Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"safety-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Safety Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Safety Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Safety Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-EHS-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO construction.ehs_incidents "
            "(id, project_id, incident_date, severity, description, corrective_action, "
            "status, created_by, updated_by, version) VALUES "
            "(:id, :project_id, :incident_date, 'major', :description, "
            ":corrective_action, :status, :actor_id, :actor_id, 1)"
        ),
        {
            "id": incident_id,
            "project_id": project_id,
            "incident_date": date(2026, 8, 23),
            "description": "SYNTHETIC PRIVATE SAFETY NARRATIVE",
            "corrective_action": corrective_action,
            "status": status,
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return actor_id, incident_id


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


async def test_ehs_refuses_direct_close_and_missing_corrective_action(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, incident_id = await _seed_incident(session)
        with pytest.raises(ConstructionConflictError):
            await ConstructionService(AllowAllIdentity()).transition_ehs_incident(
                session,
                actor_user_id=actor_id,
                incident_id=incident_id,
                target_status="closed",
            )
        await session.rollback()

        actor_id, incident_id = await _seed_incident(
            session, status="corrective_action_assigned", corrective_action=None
        )
        with pytest.raises(ConstructionConflictError, match="without corrective action"):
            await ConstructionService(AllowAllIdentity()).transition_ehs_incident(
                session,
                actor_user_id=actor_id,
                incident_id=incident_id,
                target_status="closed",
            )
        await session.rollback()
        assert await _audit_chain(session) == []


async def test_ehs_assignment_commits_minimized_valid_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, incident_id = await _seed_incident(session)
        result = await ConstructionService(AllowAllIdentity()).transition_ehs_incident(
            session,
            actor_user_id=actor_id,
            incident_id=incident_id,
            target_status="corrective_action_assigned",
            corrective_action="SYNTHETIC PRIVATE CORRECTIVE ACTION",
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert result.status == "corrective_action_assigned" and result.version == 2
        assert len(chain) == 1 and verify_chain(chain) == 1
        audit_text = chain[0].after_state
        assert audit_text is not None
        assert "SYNTHETIC PRIVATE" not in audit_text
        assert json.loads(audit_text)["corrective_action_recorded"] is True


async def test_ehs_assignment_rollback_removes_state_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, incident_id = await _seed_incident(session)
        await ConstructionService(AllowAllIdentity()).transition_ehs_incident(
            session,
            actor_user_id=actor_id,
            incident_id=incident_id,
            target_status="corrective_action_assigned",
            corrective_action="SYNTHETIC PRIVATE CORRECTIVE ACTION",
        )
        await session.rollback()
        state = (
            await session.execute(
                text(
                    "SELECT status, corrective_action, version "
                    "FROM construction.ehs_incidents WHERE id = :id"
                ),
                {"id": incident_id},
            )
        ).one()
        assert tuple(state) == ("open", None, 1)
        assert await _audit_chain(session) == []


async def test_concurrent_ehs_transition_blocks_on_incident_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, incident_id = await _seed_incident(seed)
    identity = IncidentLockProbeIdentity()

    async def assign(action: str) -> str:
        async with session_factory() as session:
            try:
                await ConstructionService(identity).transition_ehs_incident(
                    session,
                    actor_user_id=actor_id,
                    incident_id=incident_id,
                    target_status="corrective_action_assigned",
                    corrective_action=action,
                )
                await session.commit()
                return "assigned"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(assign("SYNTHETIC ACTION A"))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(assign("SYNTHETIC ACTION B"))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["assigned", "conflict"]

    async with session_factory() as session:
        state = (
            await session.execute(
                text(
                    "SELECT status, corrective_action, version "
                    "FROM construction.ehs_incidents WHERE id = :id"
                ),
                {"id": incident_id},
            )
        ).one()
        assert state.status == "corrective_action_assigned" and state.version == 2
        assert state.corrective_action in {"SYNTHETIC ACTION A", "SYNTHETIC ACTION B"}
        assert len(await _audit_chain(session)) == 1
