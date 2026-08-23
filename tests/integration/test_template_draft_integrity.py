"""Phase 5 no-code template draft integrity against PostgreSQL."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.schemas import ChecklistItem, TemplateCreate, TemplateUpdate
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


class TemplateLockProbeIdentity(AllowAllIdentity):
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


async def _seed(session: AsyncSession) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Template Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"template-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Template Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group, 'Synthetic Template Entity', 'active', 1)"
        ),
        {"id": entity_id, "group": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity, 'Synthetic Template Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity": entity_id, "code": f"SYN-TEMPLATE-{project_id}"},
    )
    await session.commit()
    return actor_id, project_id


async def _create_draft(session: AsyncSession, *, actor_id: UUID, project_id: UUID) -> UUID:
    result = await ConstructionService(AllowAllIdentity()).create_template(
        session,
        actor_user_id=actor_id,
        data=TemplateCreate(
            project_id,
            "synthetic",
            f"Synthetic Draft {uuid4()}",
            (ChecklistItem("SYNTHETIC PRIVATE INITIAL CHECK"),),
        ),
    )
    return result.id


def _update(expected_version: int, item: str) -> TemplateUpdate:
    return TemplateUpdate(
        "synthetic-updated",
        f"Synthetic Updated Draft {uuid4()}",
        (ChecklistItem(item, True),),
        expected_version,
    )


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


async def test_draft_update_commits_version_and_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id = await _seed(session)
        template_id = await _create_draft(session, actor_id=actor_id, project_id=project_id)
        await session.commit()

        updated = await ConstructionService(AllowAllIdentity()).update_template_draft(
            session,
            actor_user_id=actor_id,
            template_id=template_id,
            data=_update(1, "SYNTHETIC PRIVATE UPDATED CHECK"),
        )
        await session.commit()

        chain = await _audit_chain(session)
        assert updated.version == 2
        assert updated.checklist[0].requires_evidence
        assert [event.action for event in chain] == ["create", "update"]
        assert verify_chain(chain) == len(chain)
        assert "SYNTHETIC PRIVATE" not in "".join(event.after_state or "" for event in chain)


async def test_draft_update_rollback_restores_content_version_and_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, project_id = await _seed(session)
        template_id = await _create_draft(session, actor_id=actor_id, project_id=project_id)
        await session.commit()
        original_chain = await _audit_chain(session)

        await ConstructionService(AllowAllIdentity()).update_template_draft(
            session,
            actor_user_id=actor_id,
            template_id=template_id,
            data=_update(1, "SYNTHETIC PRIVATE ROLLBACK CHECK"),
        )
        await session.rollback()

        state = (
            await session.execute(
                text(
                    "SELECT work_package, checklist, version "
                    "FROM quality.inspection_templates WHERE id = :id"
                ),
                {"id": template_id},
            )
        ).one()
        assert state.work_package == "synthetic" and state.version == 1
        assert state.checklist[0]["item"] == "SYNTHETIC PRIVATE INITIAL CHECK"
        assert await _audit_chain(session) == original_chain


async def test_concurrent_draft_updates_allow_one_expected_version_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed:
        actor_id, project_id = await _seed(seed)
        template_id = await _create_draft(seed, actor_id=actor_id, project_id=project_id)
        await seed.commit()
    identity = TemplateLockProbeIdentity()

    async def update(item: str) -> str:
        async with session_factory() as session:
            try:
                await ConstructionService(identity).update_template_draft(
                    session,
                    actor_user_id=actor_id,
                    template_id=template_id,
                    data=_update(1, item),
                )
                await session.commit()
                return "updated"
            except ConstructionConflictError:
                await session.rollback()
                return "conflict"

    first = asyncio.create_task(update("SYNTHETIC PRIVATE CHECK A"))
    await identity.first_has_lock.wait()
    second = asyncio.create_task(update("SYNTHETIC PRIVATE CHECK B"))
    await asyncio.sleep(0.1)
    assert not second.done()
    identity.release_first.set()
    assert sorted(await asyncio.gather(first, second)) == ["conflict", "updated"]

    async with session_factory() as session:
        version = await session.scalar(
            text("SELECT version FROM quality.inspection_templates WHERE id = :id"),
            {"id": template_id},
        )
        assert version == 2
        assert [event.action for event in await _audit_chain(session)] == ["create", "update"]
