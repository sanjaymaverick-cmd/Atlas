"""Database-free tests for Phase 3 compliance invariants."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.compliance import service as service_module
from atlas.modules.compliance.contracts import ComplianceConflictError
from atlas.modules.compliance.schemas import ComplianceObligationCreate, ReraRegistrationCreate
from atlas.modules.compliance.service import ComplianceService
from atlas.modules.identity.contracts import IdentityContract

pytestmark = pytest.mark.unit


class IdentityStub:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.permissions: list[tuple[str, UUID | None, UUID | None]] = []

    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.permissions.append((permission_code, legal_entity_id, project_id))
        return self.allowed


class SessionStub:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushes = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


async def test_registration_is_scoped_versioned_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, session, events = IdentityStub(), SessionStub(), []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    project_id = uuid4()
    result = await ComplianceService(cast(IdentityContract, identity)).create_registration(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        data=ReraRegistrationCreate(project_id, "SYN-RERA-001"),
    )
    assert result.version == 1
    assert identity.permissions == [("compliance.create", None, project_id)]
    assert events[0]["action"] == "create"


async def test_obligation_requires_a_scope() -> None:
    service = ComplianceService(cast(IdentityContract, IdentityStub()))
    with pytest.raises(ComplianceConflictError, match="requires"):
        await service.create_obligation(
            cast(AsyncSession, SessionStub()),
            actor_user_id=uuid4(),
            data=ComplianceObligationCreate(None, None, "filing"),
        )
