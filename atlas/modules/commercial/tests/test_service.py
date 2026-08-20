"""Database-free Phase 4 commercial invariant tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.commercial import service as service_module
from atlas.modules.commercial.contracts import CommercialConflictError
from atlas.modules.commercial.models import Contract, PurchaseOrder
from atlas.modules.commercial.schemas import (
    BudgetCreate,
    ContractExecution,
    LabourComplianceCreate,
)
from atlas.modules.commercial.service import CommercialService
from atlas.modules.identity.contracts import IdentityContract

pytestmark = pytest.mark.unit


class IdentityStub:
    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        return True


class SessionStub:
    def __init__(self, row: object | None = None, scalar: object | None = None) -> None:
        self.row, self.scalar_value = row, scalar
        self.added: list[object] = []
        self.flushes = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1

    async def get(self, model: object, key: UUID) -> object | None:
        return self.row

    async def scalar(self, statement: object) -> object | None:
        return self.scalar_value


async def ignore_audit(*args: object, **kwargs: object) -> None:
    return None


async def test_budget_creation_is_scoped_versioned_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    session = SessionStub()
    result = await CommercialService(cast(IdentityContract, IdentityStub())).create_budget(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        data=BudgetCreate(uuid4(), uuid4(), Decimal("1000")),
    )
    assert result.version == 1 and result.status == "draft"
    assert events[0]["action"] == "create"


async def test_purchase_order_issue_requires_active_onboarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    now = datetime.now(UTC)
    row = PurchaseOrder(
        id=uuid4(),
        project_id=uuid4(),
        vendor_id=uuid4(),
        budget_line_id=None,
        total_amount=Decimal("100"),
        status="approved",
        issued_at=None,
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=3,
        archived_at=None,
    )
    with pytest.raises(CommercialConflictError, match="onboarding is active"):
        await CommercialService(cast(IdentityContract, IdentityStub())).transition_purchase_order(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=uuid4(),
            purchase_order_id=row.id,
            target_status="issued",
        )


async def test_executed_contract_requires_document_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    now = datetime.now(UTC)
    row = Contract(
        id=uuid4(),
        project_id=uuid4(),
        party_id=uuid4(),
        contract_type="synthetic",
        value=Decimal("100"),
        status="contract_execution",
        execution_method=None,
        executed_at=None,
        executed_document_id=None,
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=4,
        archived_at=None,
    )
    with pytest.raises(CommercialConflictError, match="immutable document evidence"):
        await CommercialService(cast(IdentityContract, IdentityStub())).transition_contract(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=uuid4(),
            contract_id=row.id,
            target_status="executed",
        )


async def test_execution_evidence_is_recorded_without_sensitive_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    now = datetime.now(UTC)
    row = Contract(
        id=uuid4(),
        project_id=uuid4(),
        party_id=uuid4(),
        contract_type="synthetic",
        value=Decimal("100"),
        status="contract_execution",
        execution_method=None,
        executed_at=None,
        executed_document_id=None,
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=4,
        archived_at=None,
    )
    document_id = uuid4()
    result = await CommercialService(cast(IdentityContract, IdentityStub())).transition_contract(
        cast(AsyncSession, SessionStub(row)),
        actor_user_id=uuid4(),
        contract_id=row.id,
        target_status="executed",
        execution=ContractExecution("synthetic-esign", document_id),
    )
    assert result.executed_document_id == document_id
    assert "document_reference" not in str(events[0])


async def test_labour_audit_redacts_registration_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    result = await CommercialService(
        cast(IdentityContract, IdentityStub())
    ).create_labour_compliance(
        cast(AsyncSession, SessionStub()),
        actor_user_id=uuid4(),
        data=LabourComplianceCreate(
            contractor_id=uuid4(),
            project_id=uuid4(),
            pf_registration_number="SYN-PF-REDACT",
            esi_registration_number="SYN-ESI-REDACT",
            contract_labour_licence_number="SYN-LICENCE-REDACT",
            minimum_wage_evidence_ref="SYN-EVIDENCE-REDACT",
        ),
    )
    assert result.status == "pending"
    audit_text = str(events[0])
    assert "SYN-PF-REDACT" not in audit_text
    assert "SYN-ESI-REDACT" not in audit_text
    assert "SYN-LICENCE-REDACT" not in audit_text
    assert "SYN-EVIDENCE-REDACT" not in audit_text
