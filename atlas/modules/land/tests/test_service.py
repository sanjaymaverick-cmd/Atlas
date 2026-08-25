"""Database-free tests for Phase 3 land invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.land import service as service_module
from atlas.modules.land.contracts import LandConflictError
from atlas.modules.land.models import LandParcel
from atlas.modules.land.schemas import LandParcelCreate
from atlas.modules.land.service import LandService

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
    def __init__(self, row: LandParcel | None = None) -> None:
        self.row = row
        self.added: list[object] = []
        self.flushes = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1

    async def get(self, model: object, key: UUID) -> LandParcel | None:
        return self.row


async def ignore_audit(*args: object, **kwargs: object) -> None:
    return None


async def test_parcel_creation_is_versioned_and_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    session = SessionStub()
    result = await LandService(cast(IdentityContract, IdentityStub())).create_parcel(
        cast(AsyncSession, session),
        actor_user_id=uuid4(),
        data=LandParcelCreate(uuid4(), None, "SYN-001", None, "Synthetic"),
    )
    assert result.version == 1 and events[0]["action"] == "create"


async def test_parcel_transition_rejects_skipping_due_diligence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    now = datetime.now(UTC)
    row = LandParcel(
        id=uuid4(),
        legal_entity_id=uuid4(),
        project_id=None,
        survey_number="SYN",
        area_sqft=None,
        location=None,
        acquisition_status="identified",
        status="active",
        created_at=now,
        updated_at=now,
        created_by=uuid4(),
        updated_by=uuid4(),
        version=1,
        archived_at=None,
    )
    with pytest.raises(LandConflictError, match="cannot move"):
        await LandService(cast(IdentityContract, IdentityStub())).transition_parcel(
            cast(AsyncSession, SessionStub(row)),
            actor_user_id=uuid4(),
            parcel_id=row.id,
            target_status="acquired",
        )
