"""Phase 7 workflow, evidence, scope, concurrency, and audit integrity."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.change_control.contracts import ChangeControlConflictError
from atlas.modules.change_control.schemas import (
    ChangeCreate,
    DiscrepancyCreate,
    DiscrepancyTransition,
    NcrCreate,
    NcrTransition,
    RfiCreate,
    RfiResponse,
)
from atlas.modules.change_control.service import ChangeControlService
from atlas.modules.construction.service import ConstructionService
from atlas.modules.documents.service import DocumentsService
from atlas.platform.audit.chain import AuditRecord, verify_chain

pytestmark = pytest.mark.integration


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


class TransitionLockProbeIdentity(AllowAllIdentity):
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
        database_url.replace("postgresql://", "postgresql+psycopg://"), poolclass=NullPool
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_scope(
    session: AsyncSession, *, revision_status: str = "approved"
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    actor_id, other_actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4(), uuid4()
    project_id, other_project_id, document_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) VALUES "
            "(:actor, 'Synthetic Phase 7 Actor', :actor_email, 'active', 1), "
            "(:other, 'Synthetic Phase 7 Other', :other_email, 'active', 1)"
        ),
        {
            "actor": actor_id,
            "other": other_actor_id,
            "actor_email": f"phase7-{actor_id}@example.invalid",
            "other_email": f"phase7-{other_actor_id}@example.invalid",
        },
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Phase 7 Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group, 'Synthetic Phase 7 Entity', 'active', 1)"
        ),
        {"id": entity_id, "group": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:project, :entity, 'Synthetic Phase 7 Project', :code, 'active', 1), "
            "(:other_project, :entity, 'Synthetic Other Phase 7 Project', :other_code, "
            "'active', 1)"
        ),
        {
            "project": project_id,
            "other_project": other_project_id,
            "entity": entity_id,
            "code": f"SYN-P7-{project_id}",
            "other_code": f"SYN-P7-{other_project_id}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, version) "
            "VALUES (:id, :project, 'phase7_evidence', 'restricted', 'approved', 1)"
        ),
        {"id": document_id, "project": other_project_id},
    )
    await session.execute(
        text(
            "INSERT INTO documents.document_versions "
            "(id, document_id, revision_code, object_storage_key, checksum_sha256, status) "
            "VALUES (:id, :document, 'SYN-R1', :key, :checksum, :status)"
        ),
        {
            "id": uuid4(),
            "document": document_id,
            "key": f"synthetic/phase7/{document_id}",
            "checksum": "a" * 64,
            "status": revision_status,
        },
    )
    await session.commit()
    return actor_id, other_actor_id, project_id, other_project_id, document_id


def _service(identity: AllowAllIdentity) -> ChangeControlService:
    return ChangeControlService(identity, DocumentsService(identity), ConstructionService(identity))


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


@pytest.mark.parametrize("record_type", ["change", "rfi", "ncr", "discrepancy"])
async def test_phase7_create_refuses_cross_project_controlled_evidence(
    session_factory: async_sessionmaker[AsyncSession], record_type: str
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, document_id = await _seed_scope(session)
        service = _service(AllowAllIdentity())
        with pytest.raises(ChangeControlConflictError, match="controlled evidence"):
            if record_type == "change":
                await service.create_change(
                    session,
                    actor_user_id=actor_id,
                    data=ChangeCreate(
                        project_id, "Synthetic change", evidence_document_id=document_id
                    ),
                )
            elif record_type == "rfi":
                await service.create_rfi(
                    session,
                    actor_user_id=actor_id,
                    data=RfiCreate(project_id, "Synthetic question", None, None, document_id),
                )
            elif record_type == "ncr":
                await service.create_ncr(
                    session,
                    actor_user_id=actor_id,
                    data=NcrCreate(
                        project_id,
                        "minor",
                        "Synthetic NCR",
                        evidence_document_id=document_id,
                    ),
                )
            else:
                await service.create_discrepancy(
                    session,
                    actor_user_id=actor_id,
                    data=DiscrepancyCreate(project_id, uuid4(), evidence_document_id=document_id),
                )
        await session.rollback()
        count_query = {
            "change": (
                "SELECT count(*) FROM construction.change_requests WHERE project_id = :project"
            ),
            "rfi": "SELECT count(*) FROM quality.rfis WHERE project_id = :project",
            "ncr": "SELECT count(*) FROM quality.ncrs WHERE project_id = :project",
            "discrepancy": (
                "SELECT count(*) FROM quality.discrepancy_cases WHERE project_id = :project"
            ),
        }[record_type]
        assert await session.scalar(text(count_query), {"project": project_id}) == 0
        assert await _audit_chain(session) == []


@pytest.mark.parametrize(
    "insert_statement",
    [
        "INSERT INTO construction.change_requests "
        "(id, project_id, evidence_document_id, description, version) "
        "VALUES (:id, :project, :document, 'Synthetic direct change', 1)",
        "INSERT INTO quality.rfis "
        "(id, project_id, evidence_document_id, question, version) "
        "VALUES (:id, :project, :document, 'Synthetic direct RFI', 1)",
        "INSERT INTO quality.ncrs "
        "(id, project_id, evidence_document_id, severity, description, version) "
        "VALUES (:id, :project, :document, 'minor', 'Synthetic direct NCR', 1)",
        "INSERT INTO quality.discrepancy_cases "
        "(id, project_id, evidence_document_id, description, version) "
        "VALUES (:id, :project, :document, 'Synthetic direct discrepancy', 1)",
    ],
)
async def test_database_rejects_cross_project_phase7_evidence(
    session_factory: async_sessionmaker[AsyncSession],
    insert_statement: str,
) -> None:
    async with session_factory() as session:
        _, _, project_id, _, document_id = await _seed_scope(session)
        with pytest.raises(IntegrityError):
            await session.execute(
                text(insert_statement),
                {"id": uuid4(), "project": project_id, "document": document_id},
            )
            await session.flush()
        await session.rollback()


async def test_change_path_includes_schedule_and_customer_impact_with_audited_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, requester_id, project_id, _, document_id = await _seed_scope(session)
        await session.execute(
            text("UPDATE documents.documents SET project_id = :project WHERE id = :document"),
            {"project": project_id, "document": document_id},
        )
        change_id = uuid4()
        await session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, evidence_document_id, requested_by, "
                "status, version) "
                "VALUES (:id, :project, 'Synthetic governed change', :document, :requester, "
                "'contract_impact', 8)"
            ),
            {
                "id": change_id,
                "project": project_id,
                "document": document_id,
                "requester": requester_id,
            },
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        with pytest.raises(ChangeControlConflictError, match="cannot move"):
            await service.transition_change(
                session,
                actor_user_id=actor_id,
                change_id=change_id,
                target_status="commercial_quotation",
            )
        await session.rollback()
        for status in ("schedule_impact", "customer_impact", "commercial_quotation", "approved"):
            result = await service.transition_change(
                session, actor_user_id=actor_id, change_id=change_id, target_status=status
            )
        await session.commit()
        events = [event for event in await _audit_chain(session) if event.entity_id == change_id]
        assert result.status == "approved" and result.version == 12
        assert len(events) == 4 and verify_chain(await _audit_chain(session)) >= 1
        assert "Synthetic governed change" not in str(events)


async def test_draft_evidence_cannot_authorize_change_or_discrepancy_resolution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, requester_id, project_id, _, document_id = await _seed_scope(
            session, revision_status="draft"
        )
        await session.execute(
            text("UPDATE documents.documents SET project_id = :project WHERE id = :document"),
            {"project": project_id, "document": document_id},
        )
        change_id, case_id = uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, evidence_document_id, requested_by, "
                "status, version) "
                "VALUES (:change, :project, 'Synthetic change', :document, :requester, "
                "'commercial_quotation', 10)"
            ),
            {
                "change": change_id,
                "project": project_id,
                "document": document_id,
                "requester": requester_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO quality.discrepancy_cases "
                "(id, project_id, description, evidence_document_id, proposed_resolution, "
                "status, version) VALUES (:case, :project, 'Synthetic discrepancy', :document, "
                "'Synthetic resolution', 'engineering_review', 3)"
            ),
            {
                "case": case_id,
                "project": project_id,
                "document": document_id,
            },
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        with pytest.raises(ChangeControlConflictError, match="accepted revision"):
            await service.transition_change(
                session,
                actor_user_id=actor_id,
                change_id=change_id,
                target_status="approved",
            )
        await session.rollback()
        with pytest.raises(ChangeControlConflictError, match="accepted revision"):
            await service.transition_discrepancy(
                session,
                actor_user_id=actor_id,
                case_id=case_id,
                data=DiscrepancyTransition("resolved"),
            )
        await session.rollback()
        states = (
            await session.execute(
                text(
                    "SELECT status, version FROM construction.change_requests WHERE id = :change "
                    "UNION ALL SELECT status, version FROM quality.discrepancy_cases "
                    "WHERE id = :case ORDER BY version"
                ),
                {"change": change_id, "case": case_id},
            )
        ).all()
        assert states == [("engineering_review", 3), ("commercial_quotation", 10)]


async def test_transition_row_lock_serializes_competing_change_updates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as seed_session:
        actor_id, _, project_id, _, _ = await _seed_scope(seed_session)
        change_id = uuid4()
        await seed_session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, status, version) "
                "VALUES (:id, :project, 'Synthetic concurrent change', 'requested', 1)"
            ),
            {"id": change_id, "project": project_id},
        )
        await seed_session.commit()
    identity = TransitionLockProbeIdentity()
    service = _service(identity)

    async def run(session: AsyncSession) -> str:
        try:
            await service.transition_change(
                session,
                actor_user_id=actor_id,
                change_id=change_id,
                target_status="feasibility_review",
            )
            await session.commit()
            return "committed"
        except ChangeControlConflictError:
            await session.rollback()
            return "conflict"

    async with session_factory() as first_session, session_factory() as second_session:
        first = asyncio.create_task(run(first_session))
        await asyncio.wait_for(identity.first_has_lock.wait(), timeout=2)
        second = asyncio.create_task(run(second_session))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), timeout=0.2)
        identity.release_first.set()
        assert await asyncio.wait_for(first, timeout=2) == "committed"
        assert await asyncio.wait_for(second, timeout=2) == "conflict"

    async with session_factory() as check_session:
        state = (
            await check_session.execute(
                text("SELECT status, version FROM construction.change_requests WHERE id = :id"),
                {"id": change_id},
            )
        ).one()
        assert tuple(state) == ("feasibility_review", 2)


async def test_rfi_and_ncr_replacement_evidence_is_validated_before_mutation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, cross_project_document_id = await _seed_scope(session)
        rfi_id, ncr_id = uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO quality.rfis "
                "(id, project_id, raised_by, routed_to, question, status, version) "
                "VALUES (:rfi, :project, :actor, :actor, 'Synthetic RFI', 'routed', 1)"
            ),
            {"rfi": rfi_id, "project": project_id, "actor": actor_id},
        )
        await session.execute(
            text(
                "INSERT INTO quality.ncrs "
                "(id, project_id, severity, description, status, version) "
                "VALUES (:ncr, :project, 'minor', 'Synthetic NCR', 'raised', 1)"
            ),
            {"ncr": ncr_id, "project": project_id},
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        with pytest.raises(ChangeControlConflictError, match="controlled evidence"):
            await service.respond_rfi(
                session,
                actor_user_id=actor_id,
                rfi_id=rfi_id,
                data=RfiResponse("Synthetic response", cross_project_document_id),
            )
        await session.rollback()
        with pytest.raises(ChangeControlConflictError, match="controlled evidence"):
            await service.transition_ncr(
                session,
                actor_user_id=actor_id,
                ncr_id=ncr_id,
                data=NcrTransition(
                    "corrective_action_assigned",
                    corrective_action="Synthetic correction",
                    evidence_document_id=cross_project_document_id,
                ),
            )
        await session.rollback()
        states = (
            await session.execute(
                text(
                    "SELECT status, version FROM quality.rfis WHERE id = :rfi "
                    "UNION ALL SELECT status, version FROM quality.ncrs WHERE id = :ncr"
                ),
                {"rfi": rfi_id, "ncr": ncr_id},
            )
        ).all()
        assert states == [("routed", 1), ("raised", 1)]


async def test_terminal_phase7_records_archive_once_with_minimized_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, _ = await _seed_scope(session)
        change_id, rfi_id, ncr_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, status, version) "
                "VALUES (:id, :project, 'Synthetic closed change', 'closed', 1)"
            ),
            {"id": change_id, "project": project_id},
        )
        await session.execute(
            text(
                "INSERT INTO quality.rfis (id, project_id, question, status, version) "
                "VALUES (:id, :project, 'Synthetic closed RFI', 'closed', 1)"
            ),
            {"id": rfi_id, "project": project_id},
        )
        await session.execute(
            text(
                "INSERT INTO quality.ncrs "
                "(id, project_id, severity, description, status, version) "
                "VALUES (:id, :project, 'minor', 'Synthetic closed NCR', 'closed', 1)"
            ),
            {"id": ncr_id, "project": project_id},
        )
        await session.execute(
            text(
                "INSERT INTO quality.discrepancy_cases "
                "(id, project_id, description, status, version) "
                "VALUES (:id, :project, 'Synthetic resolved discrepancy', 'resolved', 1)"
            ),
            {"id": case_id, "project": project_id},
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        first = (
            await service.archive_change(session, actor_user_id=actor_id, change_id=change_id),
            await service.archive_rfi(session, actor_user_id=actor_id, rfi_id=rfi_id),
            await service.archive_ncr(session, actor_user_id=actor_id, ncr_id=ncr_id),
            await service.archive_discrepancy(session, actor_user_id=actor_id, case_id=case_id),
        )
        await session.commit()
        retried = (
            await service.archive_change(session, actor_user_id=actor_id, change_id=change_id),
            await service.archive_rfi(session, actor_user_id=actor_id, rfi_id=rfi_id),
            await service.archive_ncr(session, actor_user_id=actor_id, ncr_id=ncr_id),
            await service.archive_discrepancy(session, actor_user_id=actor_id, case_id=case_id),
        )
        await session.commit()
        events = [
            event
            for event in await _audit_chain(session)
            if event.entity_id in {change_id, rfi_id, ncr_id, case_id}
        ]
        assert all(value.version == 2 and value.archived_at is not None for value in first)
        assert all(value.version == 2 and value.archived_at is not None for value in retried)
        assert len(events) == 4 and all(event.action == "archive" for event in events)
        assert verify_chain(await _audit_chain(session)) >= 1
        assert "Synthetic" not in str(events)


async def test_nonterminal_archive_and_archive_rollback_leave_state_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, _ = await _seed_scope(session)
        open_id, closed_id = uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO construction.change_requests "
                "(id, project_id, description, status, version) VALUES "
                "(:open, :project, 'Synthetic open change', 'requested', 1), "
                "(:closed, :project, 'Synthetic closed change', 'closed', 1)"
            ),
            {"open": open_id, "closed": closed_id, "project": project_id},
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        with pytest.raises(ChangeControlConflictError, match="terminal"):
            await service.archive_change(session, actor_user_id=actor_id, change_id=open_id)
        await session.rollback()
        audit_count = len(await _audit_chain(session))
        await service.archive_change(session, actor_user_id=actor_id, change_id=closed_id)
        await session.rollback()
        rows = (
            await session.execute(
                text(
                    "SELECT id, version, archived_at FROM construction.change_requests "
                    "WHERE id IN (:open, :closed) ORDER BY id"
                ),
                {"open": open_id, "closed": closed_id},
            )
        ).all()
        assert all(row.version == 1 and row.archived_at is None for row in rows)
        assert len(await _audit_chain(session)) == audit_count


@pytest.mark.parametrize(
    ("inspection_status", "result", "archived", "accepted"),
    [
        ("scheduled", "pending", False, False),
        ("completed", "fail", False, False),
        ("completed", "pass", True, False),
        ("completed", "pass", False, True),
    ],
)
async def test_ncr_closure_requires_active_completed_passing_reinspection(
    session_factory: async_sessionmaker[AsyncSession],
    inspection_status: str,
    result: str,
    archived: bool,
    accepted: bool,
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, _ = await _seed_scope(session)
        inspection_id, ncr_id = uuid4(), uuid4()
        await session.execute(
            text(
                "INSERT INTO quality.inspections "
                "(id, project_id, result, status, version, archived_at) "
                "VALUES (:id, :project, :result, :status, 1, "
                "CASE WHEN :archived THEN now() ELSE NULL END)"
            ),
            {
                "id": inspection_id,
                "project": project_id,
                "result": result,
                "status": inspection_status,
                "archived": archived,
            },
        )
        await session.execute(
            text(
                "INSERT INTO quality.ncrs "
                "(id, project_id, severity, description, reinspection_id, status, version) "
                "VALUES (:id, :project, 'minor', 'Synthetic NCR', :inspection, "
                "'reinspection_scheduled', 3)"
            ),
            {"id": ncr_id, "project": project_id, "inspection": inspection_id},
        )
        await session.commit()
        service = _service(AllowAllIdentity())
        if accepted:
            summary = await service.transition_ncr(
                session,
                actor_user_id=actor_id,
                ncr_id=ncr_id,
                data=NcrTransition("closed"),
            )
            await session.commit()
            assert summary.status == "closed" and summary.closed_by == actor_id
        else:
            with pytest.raises(ChangeControlConflictError, match="reinspection"):
                await service.transition_ncr(
                    session,
                    actor_user_id=actor_id,
                    ncr_id=ncr_id,
                    data=NcrTransition("closed"),
                )
            await session.rollback()
            state = (
                await session.execute(
                    text("SELECT status, version FROM quality.ncrs WHERE id = :id"),
                    {"id": ncr_id},
                )
            ).one()
            assert tuple(state) == ("reinspection_scheduled", 3)


@pytest.mark.parametrize("record_type", ["change", "rfi", "ncr", "discrepancy"])
async def test_phase7_creation_commits_or_rolls_back_with_its_audit(
    session_factory: async_sessionmaker[AsyncSession], record_type: str
) -> None:
    async with session_factory() as session:
        actor_id, _, project_id, _, _ = await _seed_scope(session)
        quantity_id = uuid4()
        if record_type == "discrepancy":
            await session.execute(
                text(
                    "INSERT INTO quantities.quantity_items "
                    "(id, project_id, calculated_quantity, status, version) "
                    "VALUES (:id, :project, 10, 'discrepancy', 1)"
                ),
                {"id": quantity_id, "project": project_id},
            )
            await session.commit()
        service = _service(AllowAllIdentity())

        async def create(label: str) -> UUID:
            if record_type == "change":
                result = await service.create_change(
                    session,
                    actor_user_id=actor_id,
                    data=ChangeCreate(project_id, f"SYNTHETIC PRIVATE CHANGE {label}"),
                )
            elif record_type == "rfi":
                result = await service.create_rfi(
                    session,
                    actor_user_id=actor_id,
                    data=RfiCreate(
                        project_id,
                        f"SYNTHETIC PRIVATE RFI {label}",
                        None,
                        None,
                    ),
                )
            elif record_type == "ncr":
                result = await service.create_ncr(
                    session,
                    actor_user_id=actor_id,
                    data=NcrCreate(
                        project_id,
                        "minor",
                        f"SYNTHETIC PRIVATE NCR {label}",
                    ),
                )
            else:
                result = await service.create_discrepancy(
                    session,
                    actor_user_id=actor_id,
                    data=DiscrepancyCreate(
                        project_id,
                        quantity_id,
                        f"SYNTHETIC PRIVATE DISCREPANCY {label}",
                    ),
                )
            return result.id

        committed_id = await create("COMMIT")
        await session.commit()
        rolled_back_id = await create("ROLLBACK")
        await session.rollback()
        count_query = {
            "change": "SELECT count(*) FROM construction.change_requests WHERE id = :id",
            "rfi": "SELECT count(*) FROM quality.rfis WHERE id = :id",
            "ncr": "SELECT count(*) FROM quality.ncrs WHERE id = :id",
            "discrepancy": "SELECT count(*) FROM quality.discrepancy_cases WHERE id = :id",
        }[record_type]
        committed_count = await session.scalar(
            text(count_query),
            {"id": committed_id},
        )
        rolled_back_count = await session.scalar(
            text(count_query),
            {"id": rolled_back_id},
        )
        events = [event for event in await _audit_chain(session) if event.entity_id == committed_id]
        assert committed_count == 1 and rolled_back_count == 0
        assert len(events) == 1 and events[0].action == "create"
        assert "SYNTHETIC PRIVATE" not in str(events)
