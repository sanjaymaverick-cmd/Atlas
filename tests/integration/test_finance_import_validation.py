"""Phase 9 import validation and audit atomicity against PostgreSQL."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.finance.contracts import FinanceConflictError
from atlas.modules.finance.service import FinanceService
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


async def _seed_pending_batch(session: AsyncSession, *, with_voucher: bool) -> tuple[UUID, UUID]:
    actor_id, group_id, entity_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    document_id, revision_id, batch_id = uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Finance Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"finance-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Finance Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Finance Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) "
            "VALUES (:id, :entity_id, 'Synthetic Finance Project', :code, 'active', 1)"
        ),
        {"id": project_id, "entity_id": entity_id, "code": f"SYN-FIN-{project_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, created_by, "
            "updated_by, version) VALUES "
            "(:id, :project_id, 'tally_export', 'restricted', 'approved', "
            ":actor_id, :actor_id, 1)"
        ),
        {"id": document_id, "project_id": project_id, "actor_id": actor_id},
    )
    await session.execute(
        text(
            "INSERT INTO documents.document_versions "
            "(id, document_id, revision_code, object_storage_key, checksum_sha256, "
            "status, author_id) VALUES "
            "(:id, :document_id, 'SYN-1', :object_key, :checksum, 'approved', :actor_id)"
        ),
        {
            "id": revision_id,
            "document_id": document_id,
            "object_key": f"synthetic/tally/{revision_id}.xml",
            "checksum": "b" * 64,
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO finance.tally_import_batches "
            "(id, legal_entity_id, source_document_id, content_sha256, status, "
            "validation_summary, created_by, updated_by, version) VALUES "
            "(:id, :entity_id, :document_id, :checksum, 'pending_validation', "
            "'{}'::jsonb, :actor_id, :actor_id, 1)"
        ),
        {
            "id": batch_id,
            "entity_id": entity_id,
            "document_id": document_id,
            "checksum": "c" * 64,
            "actor_id": actor_id,
        },
    )
    if with_voucher:
        await session.execute(
            text(
                "INSERT INTO finance.tally_vouchers "
                "(import_batch_id, legal_entity_id, project_id, external_id, voucher_type, "
                "voucher_number, voucher_date, amount, ledger_reference, currency_code, "
                "imported_at, status, created_by, updated_by, version) VALUES "
                "(:batch_id, :entity_id, :project_id, :external_id, 'Journal', "
                "'SYN-V-1', :voucher_date, :amount, 'Synthetic Ledger', 'INR', now(), 'imported', "
                ":actor_id, :actor_id, 1)"
            ),
            {
                "batch_id": batch_id,
                "entity_id": entity_id,
                "project_id": project_id,
                "external_id": f"SYN-{uuid4()}",
                "voucher_date": date(2026, 8, 23),
                "amount": Decimal("100.00"),
                "actor_id": actor_id,
            },
        )
    await session.commit()
    return actor_id, batch_id


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


async def test_validation_refuses_batch_with_preexisting_vouchers(
    async_session: AsyncSession,
) -> None:
    actor_id, batch_id = await _seed_pending_batch(async_session, with_voucher=True)

    with pytest.raises(FinanceConflictError, match="already contains vouchers"):
        await FinanceService(AllowAllIdentity()).validate_import_batch(
            async_session, actor_user_id=actor_id, batch_id=batch_id
        )
    await async_session.rollback()

    state = (
        await async_session.execute(
            text(
                "SELECT status, validation_summary, version "
                "FROM finance.tally_import_batches WHERE id = :id"
            ),
            {"id": batch_id},
        )
    ).one()
    assert tuple(state) == ("pending_validation", {}, 1)
    assert await _audit_chain(async_session) == []


async def test_validation_commits_state_and_one_valid_audit_event(
    async_session: AsyncSession,
) -> None:
    actor_id, batch_id = await _seed_pending_batch(async_session, with_voucher=False)

    validated = await FinanceService(AllowAllIdentity()).validate_import_batch(
        async_session, actor_user_id=actor_id, batch_id=batch_id
    )
    await async_session.commit()

    chain = await _audit_chain(async_session)
    assert validated.status == "validated" and validated.version == 2
    assert [(event.entity_schema, event.entity_table, event.action) for event in chain] == [
        ("finance", "tally_import_batches", "validate")
    ]
    assert verify_chain(chain) == 1


async def test_validation_rollback_removes_state_and_audit(
    async_session: AsyncSession,
) -> None:
    actor_id, batch_id = await _seed_pending_batch(async_session, with_voucher=False)

    await FinanceService(AllowAllIdentity()).validate_import_batch(
        async_session, actor_user_id=actor_id, batch_id=batch_id
    )
    await async_session.rollback()

    state = (
        await async_session.execute(
            text(
                "SELECT status, validation_summary, version "
                "FROM finance.tally_import_batches WHERE id = :id"
            ),
            {"id": batch_id},
        )
    ).one()
    assert tuple(state) == ("pending_validation", {}, 1)
    assert await _audit_chain(async_session) == []
