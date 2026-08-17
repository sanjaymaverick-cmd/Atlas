"""Database-free Phase 5 construction and quality invariant tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.construction import service as service_module
from atlas.modules.construction.contracts import ConstructionConflictError
from atlas.modules.construction.models import SiteDiaryEntry
from atlas.modules.construction.schemas import EhsCreate, SiteDiaryCreate
from atlas.modules.construction.service import ConstructionService
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
    def __init__(self, *, scalar: object | None = None) -> None:
        self.scalar_value = scalar
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def scalar(self, statement: object) -> object | None:
        return self.scalar_value


def service() -> ConstructionService:
    return ConstructionService(cast(IdentityContract, IdentityStub()))


async def test_ehs_audit_omits_sensitive_narrative(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    result = await service().create_ehs_incident(
        cast(AsyncSession, SessionStub()),
        actor_user_id=uuid4(),
        data=EhsCreate(
            uuid4(), date(2026, 8, 17), "major", description="SYNTHETIC PRIVATE NARRATIVE"
        ),
    )
    assert result.status == "open"
    assert "SYNTHETIC PRIVATE NARRATIVE" not in str(events)


async def test_ehs_rejects_unknown_severity_before_write() -> None:
    session = SessionStub()
    with pytest.raises(ConstructionConflictError, match="severity"):
        await service().create_ehs_incident(
            cast(AsyncSession, session),
            actor_user_id=uuid4(),
            data=EhsCreate(uuid4(), date(2026, 8, 17), "unknown"),
        )
    assert session.added == []


@pytest.mark.parametrize("severity", ["near_miss", "minor", "major", "fatality"])
async def test_ehs_severity_matches_canonical_database_values(
    monkeypatch: pytest.MonkeyPatch, severity: str
) -> None:
    async def audit(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(service_module, "record_event", audit)
    result = await service().create_ehs_incident(
        cast(AsyncSession, SessionStub()),
        actor_user_id=uuid4(),
        data=EhsCreate(uuid4(), date(2026, 8, 17), severity),
    )
    assert result.severity == severity


async def test_offline_diary_client_id_cannot_silently_change_date() -> None:
    now = datetime.now(UTC)
    project_id, client_id, actor = uuid4(), uuid4(), uuid4()
    existing = SiteDiaryEntry(
        id=uuid4(),
        project_id=project_id,
        entry_date=date(2026, 8, 16),
        client_record_id=client_id,
        device_recorded_at=now,
        weather=None,
        labour_strength={},
        materials_received=[],
        materials_consumed=[],
        equipment_breakdowns=None,
        visitor_log=[{"count": 0}],
        site_instructions=None,
        delays_and_reasons=None,
        recorded_by=actor,
        status="submitted",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        version=1,
        archived_at=None,
    )
    data = SiteDiaryCreate(
        project_id, date(2026, 8, 17), client_id, now, None, {}, (), (), None, 0, None, None
    )
    with pytest.raises(ConstructionConflictError, match="another diary date"):
        await service().submit_site_diary(
            cast(AsyncSession, SessionStub(scalar=existing)), actor_user_id=actor, data=data
        )
