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
from atlas.modules.commercial.schemas import ContractExecution
from atlas.modules.commercial.service import CommercialService
from atlas.modules.documents.service import DocumentsService
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


async def _seed_contract_evidence(
    session: AsyncSession,
    *,
    same_project: bool,
    document_status: str,
    revision_status: str,
) -> tuple[UUID, UUID, UUID]:
    actor_id, group_id, entity_id = uuid4(), uuid4(), uuid4()
    contract_project_id, evidence_project_id = uuid4(), uuid4()
    party_id, contract_id, document_id, revision_id = uuid4(), uuid4(), uuid4(), uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic Contract Actor', :email, 'active', 1)"
        ),
        {"id": actor_id, "email": f"contract-actor-{actor_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO organization.business_groups (id, name, status, version) "
            "VALUES (:id, 'Synthetic Contract Group', 'active', 1)"
        ),
        {"id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.legal_entities "
            "(id, business_group_id, name, status, version) "
            "VALUES (:id, :group_id, 'Synthetic Contract Entity', 'active', 1)"
        ),
        {"id": entity_id, "group_id": group_id},
    )
    await session.execute(
        text(
            "INSERT INTO organization.projects "
            "(id, legal_entity_id, name, code, status, version) VALUES "
            "(:contract_project, :entity_id, 'Synthetic Contract Project', :contract_code, "
            "'active', 1), "
            "(:evidence_project, :entity_id, 'Synthetic Evidence Project', :evidence_code, "
            "'active', 1)"
        ),
        {
            "contract_project": contract_project_id,
            "evidence_project": evidence_project_id,
            "entity_id": entity_id,
            "contract_code": f"SYN-CON-{contract_project_id}",
            "evidence_code": f"SYN-EVD-{evidence_project_id}",
        },
    )
    await session.execute(
        text(
            "INSERT INTO organization.parties "
            "(id, party_type, legal_name, status, version) "
            "VALUES (:id, 'vendor', 'Synthetic Contract Party', 'active', 1)"
        ),
        {"id": party_id},
    )
    await session.execute(
        text(
            "INSERT INTO contracts.contracts "
            "(id, project_id, party_id, contract_type, value, status, created_by, "
            "updated_by, version) VALUES "
            "(:id, :project_id, :party_id, 'synthetic', 100, 'contract_execution', "
            ":actor_id, :actor_id, 4)"
        ),
        {
            "id": contract_id,
            "project_id": contract_project_id,
            "party_id": party_id,
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO documents.documents "
            "(id, project_id, document_type, classification, status, created_by, "
            "updated_by, version) VALUES "
            "(:id, :project_id, 'executed_contract', 'restricted', :status, "
            ":actor_id, :actor_id, 1)"
        ),
        {
            "id": document_id,
            "project_id": contract_project_id if same_project else evidence_project_id,
            "status": document_status,
            "actor_id": actor_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO documents.document_versions "
            "(id, document_id, revision_code, object_storage_key, checksum_sha256, "
            "status, author_id) VALUES "
            "(:id, :document_id, 'SYN-1', :object_key, :checksum, :status, :actor_id)"
        ),
        {
            "id": revision_id,
            "document_id": document_id,
            "object_key": f"synthetic/contracts/{revision_id}.pdf",
            "checksum": "a" * 64,
            "status": revision_status,
            "actor_id": actor_id,
        },
    )
    await session.commit()
    return actor_id, contract_id, document_id


def _commercial_with_documents() -> CommercialService:
    identity = AllowAllIdentity()
    return CommercialService(identity, DocumentsService(identity))


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


@pytest.mark.parametrize(
    ("same_project", "document_status", "revision_status"),
    [
        (False, "approved", "approved"),
        (True, "uploaded", "draft"),
        (True, "approved", "draft"),
    ],
)
async def test_contract_execution_rejects_uncontrolled_document_evidence(
    async_session: AsyncSession,
    *,
    same_project: bool,
    document_status: str,
    revision_status: str,
) -> None:
    actor_id, contract_id, document_id = await _seed_contract_evidence(
        async_session,
        same_project=same_project,
        document_status=document_status,
        revision_status=revision_status,
    )

    with pytest.raises(CommercialConflictError, match="document evidence"):
        await _commercial_with_documents().transition_contract(
            async_session,
            actor_user_id=actor_id,
            contract_id=contract_id,
            target_status="executed",
            execution=ContractExecution("synthetic-esign", document_id),
        )
    await async_session.rollback()

    state = (
        await async_session.execute(
            text(
                "SELECT status, executed_document_id, executed_at, version "
                "FROM contracts.contracts WHERE id = :id"
            ),
            {"id": contract_id},
        )
    ).one()
    assert tuple(state) == ("contract_execution", None, None, 4)
    assert await _audit_chain(async_session) == []


async def test_contract_execution_commits_controlled_document_and_audit(
    async_session: AsyncSession,
) -> None:
    actor_id, contract_id, document_id = await _seed_contract_evidence(
        async_session,
        same_project=True,
        document_status="approved",
        revision_status="approved",
    )

    executed = await _commercial_with_documents().transition_contract(
        async_session,
        actor_user_id=actor_id,
        contract_id=contract_id,
        target_status="executed",
        execution=ContractExecution("synthetic-esign", document_id),
    )
    await async_session.commit()

    chain = await _audit_chain(async_session)
    assert executed.status == "executed"
    assert executed.executed_document_id == document_id
    assert executed.executed_at is not None and executed.version == 5
    assert [(event.entity_schema, event.entity_table, event.action) for event in chain] == [
        ("contracts", "contracts", "transition")
    ]
    assert verify_chain(chain) == 1
