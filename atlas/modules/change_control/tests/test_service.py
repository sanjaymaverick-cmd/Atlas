"""Database-free Phase 7 state-machine and privacy tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.change_control import service as service_module
from atlas.modules.change_control.contracts import (
    ChangeControlConflictError,
    ChangeControlNotAuthorisedError,
)
from atlas.modules.change_control.models import ChangeRequest, DiscrepancyCase, Rfi
from atlas.modules.change_control.schemas import ChangeCreate, DiscrepancyTransition, RfiResponse
from atlas.modules.change_control.service import ChangeControlService
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
    def __init__(self, row: object | None = None) -> None:
        self.row = row
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, model: object, key: UUID) -> object | None:
        return self.row


def service() -> ChangeControlService:
    return ChangeControlService(cast(IdentityContract, IdentityStub()))


async def no_audit(*args: object, **kwargs: object) -> None:
    return None


async def test_change_audit_omits_confidential_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    result = await service().create_change(
        cast(AsyncSession, SessionStub()),
        actor_user_id=uuid4(),
        data=ChangeCreate(uuid4(), "SYNTHETIC CONFIDENTIAL CHANGE", "SYNTHETIC SCHEDULE DETAIL"),
    )
    assert result.status == "requested"
    assert "SYNTHETIC CONFIDENTIAL" not in str(events)
    assert "SYNTHETIC SCHEDULE" not in str(events)


async def test_change_approval_requires_controlled_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    row = ChangeRequest(
        id=uuid4(),
        project_id=uuid4(),
        description="synthetic",
        schedule_impact=None,
        budget_impact=None,
        evidence_document_id=None,
        requested_by=uuid4(),
        decided_by=None,
        decided_at=None,
        status="commercial_quotation",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=9,
        archived_at=None,
    )
    with pytest.raises(ChangeControlConflictError, match="controlled evidence"):
        await service().transition_change(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=actor,
            change_id=row.id,
            target_status="approved",
        )


async def test_only_routed_recipient_may_respond(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    row = Rfi(
        id=uuid4(),
        project_id=uuid4(),
        raised_by=uuid4(),
        routed_to=uuid4(),
        question="synthetic",
        response=None,
        evidence_document_id=None,
        responded_by=None,
        responded_at=None,
        sla_due_at=None,
        status="routed",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    with pytest.raises(ChangeControlNotAuthorisedError, match="routed recipient"):
        await service().respond_rfi(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=actor,
            rfi_id=row.id,
            data=RfiResponse("SYNTHETIC PRIVATE RESPONSE"),
        )


async def test_discrepancy_resolution_requires_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    now = datetime.now(UTC)
    actor = uuid4()
    row = DiscrepancyCase(
        id=uuid4(),
        project_id=uuid4(),
        quantity_item_id=uuid4(),
        description=None,
        evidence_ref=None,
        evidence_document_id=None,
        proposed_resolution="synthetic",
        resolved_by=None,
        resolved_at=None,
        status="engineering_review",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=3,
        archived_at=None,
    )
    with pytest.raises(ChangeControlConflictError, match="controlled evidence"):
        await service().transition_discrepancy(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=actor,
            case_id=row.id,
            data=DiscrepancyTransition("resolved"),
        )
