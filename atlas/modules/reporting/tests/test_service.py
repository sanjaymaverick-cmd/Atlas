"""Database-free Phase 10 separation and privacy tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.reporting import service as service_module
from atlas.modules.reporting.contracts import ReportingConflictError
from atlas.modules.reporting.models import ProjectSummaryView
from atlas.modules.reporting.schemas import ReportRequestCreate
from atlas.modules.reporting.service import ReportingService

pytestmark = pytest.mark.unit


class IdentityStub:
    def __init__(self) -> None:
        self.sessions: list[object] = []

    async def check_scoped_role(
        self,
        session: object,
        *,
        user_id: UUID,
        permission_code: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        self.sessions.append(session)
        return True


class ResultStub:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class SessionStub:
    def __init__(self, row: object | None = None, rows: Sequence[object] | None = None) -> None:
        self.row = row
        self.rows = list(rows or [])
        self.added: list[object] = []
        self.gets = 0
        self.flushes = 0

    async def get(self, model: type[object], key: UUID) -> object | None:
        self.gets += 1
        return self.row

    async def scalars(self, statement: object) -> ResultStub:
        return ResultStub(self.rows)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


def summary(project: UUID, entity: UUID) -> ProjectSummaryView:
    return ProjectSummaryView(
        project_id=project,
        legal_entity_id=entity,
        planned_amount=Decimal("100"),
        committed_amount=Decimal("80"),
        actual_amount=Decimal("60"),
        approved_po_amount=Decimal("70"),
        released_payment_amount=Decimal("50"),
        allocated_collection_amount=Decimal("40"),
        outstanding_receivable_amount=Decimal("10"),
        unallocated_collection_count=1,
        overdue_installment_count=2,
        delayed_activity_count=3,
        failed_inspection_count=4,
        open_compliance_count=5,
        open_reconciliation_count=6,
        total_unit_count=10,
        available_unit_count=4,
        committed_unit_count=6,
        refreshed_at=datetime.now(UTC),
    )


async def no_audit(*args: object, **kwargs: object) -> None:
    return None


async def test_dashboard_reads_reporting_session_and_authorises_on_primary() -> None:
    identity = IdentityStub()
    project, entity = uuid4(), uuid4()
    primary = SessionStub()
    replica = SessionStub(summary(project, entity))
    result = await ReportingService(cast(IdentityContract, identity)).get_project_dashboard(
        cast(AsyncSession, primary),
        cast(AsyncSession, replica),
        actor_user_id=uuid4(),
        project_id=project,
    )
    assert result.project_id == project
    assert identity.sessions == [primary]
    assert primary.gets == 0
    assert replica.gets == 1


async def test_entity_dashboard_aggregates_without_identity_fields() -> None:
    identity = IdentityStub()
    entity = uuid4()
    rows = [summary(uuid4(), entity), summary(uuid4(), entity)]
    result = await ReportingService(cast(IdentityContract, identity)).get_entity_dashboard(
        cast(AsyncSession, SessionStub()),
        cast(AsyncSession, SessionStub(rows=rows)),
        actor_user_id=uuid4(),
        legal_entity_id=entity,
    )
    assert result.project_count == 2
    assert result.planned_amount == Decimal("200")
    assert not hasattr(result, "customer_name")


async def test_report_request_rejects_cross_entity_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "record_event", no_audit)
    identity = IdentityStub()
    entity = uuid4()
    project = uuid4()
    with pytest.raises(ReportingConflictError, match="does not belong"):
        await ReportingService(cast(IdentityContract, identity)).create_report_request(
            cast(AsyncSession, SessionStub()),
            cast(AsyncSession, SessionStub(summary(project, uuid4()))),
            actor_user_id=uuid4(),
            data=ReportRequestCreate(entity, "ceo_project_summary", "pdf", project),
        )


async def test_report_request_is_written_and_audited_on_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def audit(*args: object, **kwargs: object) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service_module, "record_event", audit)
    identity = IdentityStub()
    entity = uuid4()
    project = uuid4()
    primary = SessionStub()
    replica = SessionStub(summary(project, entity))
    result = await ReportingService(cast(IdentityContract, identity)).create_report_request(
        cast(AsyncSession, primary),
        cast(AsyncSession, replica),
        actor_user_id=uuid4(),
        data=ReportRequestCreate(entity, "ceo_project_summary", "xlsx", project),
    )
    assert result.status == "queued"
    assert len(primary.added) == 1
    assert primary.flushes == 1
    assert events[0]["entity_table"] == "report_requests"
