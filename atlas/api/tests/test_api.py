"""HTTP behavior through injected module contracts and synthetic records."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from atlas.api import application
from atlas.api.application import create_app
from atlas.modules.change_control.schemas import ChangeCreate, ChangeSummary
from atlas.modules.commercial.schemas import BudgetCreate, BudgetSummary
from atlas.modules.compliance.schemas import (
    ComplianceObligationCreate,
    ComplianceObligationSummary,
)
from atlas.modules.construction.schemas import SiteDiaryCreate, SiteDiarySummary
from atlas.modules.customer_lifecycle.schemas import BookingCreate, BookingSummary
from atlas.modules.documents.contracts import DocumentConflictError
from atlas.modules.documents.schemas import (
    DocumentCreate,
    DocumentSummary,
    ExportRequestSummary,
    PreviewGrant,
    RevisionCreate,
    RevisionSummary,
)
from atlas.modules.identity.contracts import InvalidCeremonyError
from atlas.modules.identity.schemas import (
    AuthenticationOutcome,
    CeremonyOptions,
    RelyingParty,
    SessionContext,
)
from atlas.modules.land.schemas import LandParcelCreate, LandParcelSummary
from atlas.modules.organization.contracts import ConflictError, NotAuthorisedError, NotFoundError
from atlas.modules.organization.schemas import ProjectCreate, ProjectSummary, ProjectUpdate
from atlas.modules.project_controls.schemas import BimImportCreate, BimImportSummary
from atlas.platform.access_control import DeviceTrust

pytestmark = pytest.mark.unit

ACTOR_ID = UUID("11111111-1111-1111-1111-111111111111")
ENTITY_ID = UUID("22222222-2222-2222-2222-222222222222")
PROJECT_ID = UUID("33333333-3333-3333-3333-333333333333")
DOCUMENT_ID = UUID("44444444-4444-4444-4444-444444444444")
REVISION_ID = UUID("55555555-5555-5555-5555-555555555555")
PARCEL_ID = UUID("66666666-6666-6666-6666-666666666666")
OBLIGATION_ID = UUID("77777777-7777-7777-7777-777777777777")


def project(*, archived: bool = False, version: int = 1) -> ProjectSummary:
    return ProjectSummary(
        id=PROJECT_ID,
        legal_entity_id=ENTITY_ID,
        name="Synthetic Heights",
        code="SYN-001",
        city="Test City",
        status="planning",
        start_date=date(2026, 9, 1),
        target_completion_date=None,
        version=version,
        archived_at=datetime(2026, 8, 17, tzinfo=UTC) if archived else None,
    )


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession()
        self.sessions.append(session)
        return session


class FakeConnection:
    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        return None


class FailingConnection(FakeConnection):
    async def __aenter__(self) -> FakeConnection:
        raise SQLAlchemyError("synthetic database failure")


class FakeEngine:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.disposed = False

    def connect(self) -> AbstractAsyncContextManager[FakeConnection]:
        return FakeConnection() if self.ready else FailingConnection()

    async def dispose(self) -> None:
        self.disposed = True


class FakeIdentity:
    def __init__(
        self, *, authenticated: bool = True, step_up: bool = False, risk_score: float = 0
    ) -> None:
        self.authenticated = authenticated
        self.step_up = step_up
        self.risk_score = risk_score
        self.tokens: list[str] = []
        self.ceremony_failure: Exception | None = None
        self.clone_detected = False

    async def authenticate_session_token(
        self, session: object, token: str
    ) -> SessionContext | None:
        self.tokens.append(token)
        if not self.authenticated:
            return None
        return SessionContext(
            session_id=uuid4(),
            user_id=ACTOR_ID,
            device_id=uuid4(),
            user_status="active",
            device_status="active",
            device_trust=DeviceTrust.ELEVATED,
            risk_score=self.risk_score,
            step_up_verified=self.step_up,
            step_up_verified_at=datetime.now(UTC) if self.step_up else None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            revoked_at=None,
        )

    async def begin_registration(
        self, session: object, *, user_id: UUID, rp: RelyingParty
    ) -> CeremonyOptions:
        return CeremonyOptions(
            ceremony_id=PROJECT_ID,
            public_key={"challenge": "synthetic-registration-challenge", "rp": {"id": rp.rp_id}},
        )

    async def complete_registration(
        self,
        session: object,
        *,
        ceremony_id: UUID,
        credential: dict[str, object],
        device_name: str | None,
        rp: RelyingParty,
    ) -> UUID:
        if self.ceremony_failure is not None:
            raise self.ceremony_failure
        return PROJECT_ID

    async def begin_authentication(self, session: object, *, rp: RelyingParty) -> CeremonyOptions:
        return CeremonyOptions(
            ceremony_id=PROJECT_ID,
            public_key={"challenge": "synthetic-authentication-challenge", "rpId": rp.rp_id},
        )

    async def complete_authentication(
        self,
        session: object,
        *,
        ceremony_id: UUID,
        credential: dict[str, object],
        rp: RelyingParty,
    ) -> AuthenticationOutcome:
        if self.ceremony_failure is not None:
            raise self.ceremony_failure
        if self.clone_detected:
            return AuthenticationOutcome(None, None, clone_detected=True)
        return AuthenticationOutcome(
            "synthetic-opaque-token",
            datetime(2026, 8, 18, tzinfo=UTC),
        )


class FakeOrganization:
    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.calls: list[tuple[str, UUID, object]] = []

    def _raise_if_needed(self) -> None:
        if self.failure is not None:
            raise self.failure

    async def unit_belongs_to_project(
        self, session: object, *, unit_id: UUID, project_id: UUID
    ) -> bool:
        return True

    async def get_project(
        self, session: object, *, actor_user_id: UUID, project_id: UUID
    ) -> ProjectSummary:
        self._raise_if_needed()
        self.calls.append(("get", actor_user_id, project_id))
        return project()

    async def list_projects(
        self, session: object, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[ProjectSummary]:
        self._raise_if_needed()
        self.calls.append(("list", actor_user_id, legal_entity_id))
        return [project()]

    async def create_project(
        self, session: object, *, actor_user_id: UUID, data: ProjectCreate
    ) -> ProjectSummary:
        self._raise_if_needed()
        self.calls.append(("create", actor_user_id, data))
        return project()

    async def update_project(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        project_id: UUID,
        data: ProjectUpdate,
    ) -> ProjectSummary:
        self._raise_if_needed()
        self.calls.append(("update", actor_user_id, data))
        return project(version=2)

    async def archive_project(
        self, session: object, *, actor_user_id: UUID, project_id: UUID
    ) -> ProjectSummary:
        self._raise_if_needed()
        self.calls.append(("archive", actor_user_id, project_id))
        return project(archived=True, version=2)


class FakeLand:
    def __init__(self) -> None:
        self.calls: list[LandParcelCreate] = []

    async def create_parcel(
        self, session: object, *, actor_user_id: UUID, data: LandParcelCreate
    ) -> LandParcelSummary:
        self.calls.append(data)
        return LandParcelSummary(
            PARCEL_ID,
            data.legal_entity_id,
            data.project_id,
            data.survey_number,
            data.area_sqft,
            data.location,
            "identified",
            "active",
            1,
            None,
        )


class FakeCompliance:
    def __init__(self) -> None:
        self.calls: list[ComplianceObligationCreate] = []

    async def create_obligation(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        data: ComplianceObligationCreate,
    ) -> ComplianceObligationSummary:
        self.calls.append(data)
        return ComplianceObligationSummary(
            OBLIGATION_ID,
            data.legal_entity_id,
            data.project_id,
            data.obligation_type,
            data.authority,
            data.due_date,
            data.amount,
            "open",
            1,
            None,
        )


class FakeCommercial:
    def __init__(self) -> None:
        self.calls: list[BudgetCreate] = []

    async def create_budget(
        self, session: object, *, actor_user_id: UUID, data: BudgetCreate
    ) -> BudgetSummary:
        self.calls.append(data)
        return BudgetSummary(
            uuid4(),
            data.project_id,
            data.legal_entity_id,
            data.total_amount,
            "draft",
            None,
            1,
            None,
        )


class FakeConstruction:
    def __init__(self) -> None:
        self.calls: list[SiteDiaryCreate] = []

    async def submit_site_diary(
        self, session: object, *, actor_user_id: UUID, data: SiteDiaryCreate
    ) -> SiteDiarySummary:
        self.calls.append(data)
        return SiteDiarySummary(
            uuid4(), data.project_id, data.entry_date, data.client_record_id, "submitted", 1, None
        )


class FakeProjectControls:
    def __init__(self) -> None:
        self.calls: list[BimImportCreate] = []

    async def register_bim_import(
        self, session: object, *, actor_user_id: UUID, data: BimImportCreate
    ) -> BimImportSummary:
        self.calls.append(data)
        return BimImportSummary(
            uuid4(), data.project_id, data.source_document_id, "received", None, None, 1
        )


class FakeChangeControl:
    def __init__(self) -> None:
        self.calls: list[ChangeCreate] = []

    async def create_change(
        self, session: object, *, actor_user_id: UUID, data: ChangeCreate
    ) -> ChangeSummary:
        self.calls.append(data)
        return ChangeSummary(
            uuid4(), data.project_id, "requested", data.evidence_document_id, None, None, 1
        )


class FakeCustomerLifecycle:
    def __init__(self) -> None:
        self.calls: list[BookingCreate] = []

    async def create_booking(
        self, session: object, *, actor_user_id: UUID, data: BookingCreate
    ) -> BookingSummary:
        self.calls.append(data)
        return BookingSummary(
            uuid4(),
            data.project_id,
            data.customer_id,
            data.unit_id,
            data.booking_date,
            data.booking_document_id,
            "booked",
            1,
        )


class FakeDocuments:
    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.calls: list[tuple[str, UUID, object]] = []

    def _document(self, *, archived: bool = False, version: int = 1) -> DocumentSummary:
        return DocumentSummary(
            id=DOCUMENT_ID,
            project_id=PROJECT_ID,
            discipline="architectural",
            drawing_number="SYN-A-001",
            document_type="drawing",
            classification="confidential",
            status="archived" if archived else "uploaded",
            version=version,
            archived_at=datetime.now(UTC) if archived else None,
        )

    def _raise(self) -> None:
        if self.failure is not None:
            raise self.failure

    async def get_document(
        self, session: object, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary:
        self._raise()
        self.calls.append(("get_document", actor_user_id, document_id))
        return self._document()

    async def list_documents(
        self, session: object, *, actor_user_id: UUID, project_id: UUID
    ) -> list[DocumentSummary]:
        self._raise()
        self.calls.append(("list_documents", actor_user_id, project_id))
        return [self._document()]

    async def create_document(
        self, session: object, *, actor_user_id: UUID, data: DocumentCreate
    ) -> DocumentSummary:
        self._raise()
        self.calls.append(("create_document", actor_user_id, data))
        return self._document()

    async def add_revision(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        data: RevisionCreate,
    ) -> RevisionSummary:
        self._raise()
        self.calls.append(("add_revision", actor_user_id, data))
        return RevisionSummary(
            id=REVISION_ID,
            document_id=document_id,
            revision_code=data.revision_code,
            issue_purpose=data.issue_purpose,
            issue_date=data.issue_date,
            author_id=actor_user_id,
            superseded_version_id=None,
            object_storage_key=data.object_storage_key,
            checksum_sha256=data.checksum_sha256,
            status="draft",
            created_at=datetime.now(UTC),
        )

    async def add_revision_content(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        document_id: UUID,
        revision_code: str,
        content: bytes,
        issue_purpose: str | None,
        issue_date: date | None,
    ) -> RevisionSummary:
        return await self.add_revision(
            session,
            actor_user_id=actor_user_id,
            document_id=document_id,
            data=RevisionCreate(
                revision_code,
                "server/generated/synthetic-object",
                "a" * 64,
                issue_purpose,
                issue_date,
            ),
        )

    async def list_revisions(
        self, session: object, *, actor_user_id: UUID, document_id: UUID
    ) -> list[RevisionSummary]:
        return [
            await self.add_revision(
                session,
                actor_user_id=actor_user_id,
                document_id=document_id,
                data=RevisionCreate("A", "synthetic/object", "a" * 64),
            )
        ]

    async def archive_document(
        self, session: object, *, actor_user_id: UUID, document_id: UUID
    ) -> DocumentSummary:
        self._raise()
        self.calls.append(("archive_document", actor_user_id, document_id))
        return self._document(archived=True, version=2)

    async def record_scan_result(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        clean: bool,
    ) -> RevisionSummary:
        value = await self.add_revision(
            session,
            actor_user_id=actor_user_id,
            document_id=DOCUMENT_ID,
            data=RevisionCreate("A", "synthetic/object", "a" * 64),
        )
        return replace(value, status="virus_scanned" if clean else "quarantined")

    async def transition_revision(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        target_status: str,
    ) -> RevisionSummary:
        value = await self.record_scan_result(
            session,
            actor_user_id=actor_user_id,
            revision_id=revision_id,
            clean=True,
        )
        return replace(value, status=target_status)

    async def create_preview_grant(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        revision_id: UUID,
        device_trust: DeviceTrust,
    ) -> PreviewGrant:
        return PreviewGrant(
            id=REVISION_ID,
            token="synthetic-preview-token",  # noqa: S106
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            watermark_text=f"ATLAS user:{actor_user_id} session:{session_id}",
        )

    async def render_preview(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        session_id: UUID,
        token: str,
        device_trust: DeviceTrust,
    ) -> bytes:
        return b"%PDF-1.7\n% synthetic watermarked preview"

    async def request_export(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        revision_id: UUID,
        reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary:
        return ExportRequestSummary(
            id=REVISION_ID,
            document_version_id=revision_id,
            requested_by=actor_user_id,
            approved_by=None,
            reason=reason,
            decision_reason=None,
            status="pending",
            expires_at=None,
            version=1,
        )

    async def decide_export(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        approve: bool,
        decision_reason: str,
        device_trust: DeviceTrust,
    ) -> ExportRequestSummary:
        return ExportRequestSummary(
            id=request_id,
            document_version_id=REVISION_ID,
            requested_by=uuid4(),
            approved_by=actor_user_id,
            reason="Synthetic export",
            decision_reason=decision_reason,
            status="approved" if approve else "rejected",
            expires_at=datetime.now(UTC) + timedelta(minutes=15) if approve else None,
            version=2,
        )

    async def download_export(
        self,
        session: object,
        *,
        actor_user_id: UUID,
        request_id: UUID,
        device_trust: DeviceTrust,
    ) -> bytes:
        return b"synthetic controlled export"


def build_client(
    *,
    engine: FakeEngine | None = None,
    identity: FakeIdentity | None = None,
    organization: FakeOrganization | None = None,
    documents: FakeDocuments | None = None,
    land: FakeLand | None = None,
    compliance: FakeCompliance | None = None,
    commercial: FakeCommercial | None = None,
    construction: FakeConstruction | None = None,
    project_controls: FakeProjectControls | None = None,
    change_control: FakeChangeControl | None = None,
    customer_lifecycle: FakeCustomerLifecycle | None = None,
) -> tuple[httpx.AsyncClient, FakeOrganization, FakeSessionFactory]:
    fake_organization = organization or FakeOrganization()
    session_factory = FakeSessionFactory()
    app = create_app(
        engine=engine or FakeEngine(),  # type: ignore[arg-type]
        session_factory=session_factory,  # type: ignore[arg-type]
        identity_service=identity or FakeIdentity(),  # type: ignore[arg-type]
        organization_service=fake_organization,
        documents_service=documents or FakeDocuments(),
        land_service=land or FakeLand(),  # type: ignore[arg-type]
        compliance_service=compliance or FakeCompliance(),  # type: ignore[arg-type]
        commercial_service=commercial or FakeCommercial(),  # type: ignore[arg-type]
        construction_service=construction or FakeConstruction(),  # type: ignore[arg-type]
        project_controls_service=project_controls or FakeProjectControls(),  # type: ignore[arg-type]
        change_control_service=change_control or FakeChangeControl(),  # type: ignore[arg-type]
        customer_lifecycle_service=customer_lifecycle or FakeCustomerLifecycle(),  # type: ignore[arg-type]
        relying_party=RelyingParty(
            rp_id="localhost", rp_name="Atlas Test", origin="http://localhost"
        ),
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer synthetic-session-token"},
    )
    return client, fake_organization, session_factory


async def test_phase3_routes_delegate_to_published_contracts() -> None:
    land = FakeLand()
    compliance = FakeCompliance()
    client, _, sessions = build_client(land=land, compliance=compliance)
    async with client:
        parcel = await client.post(
            f"/api/v1/legal-entities/{ENTITY_ID}/land-parcels",
            json={
                "project_id": str(PROJECT_ID),
                "survey_number": "SYN-SURVEY-001",
                "area_sqft": "1200.50",
                "location": "Synthetic location",
            },
        )
        obligation = await client.post(
            "/api/v1/compliance-obligations",
            json={
                "project_id": str(PROJECT_ID),
                "obligation_type": "synthetic_filing",
                "authority": "Synthetic Authority",
                "amount": "100.00",
            },
        )
    assert parcel.status_code == 201
    assert parcel.json()["acquisition_status"] == "identified"
    assert land.calls[0].legal_entity_id == ENTITY_ID
    assert obligation.status_code == 201
    assert obligation.json()["status"] == "open"
    assert compliance.calls[0].project_id == PROJECT_ID
    assert [session.commits for session in sessions.sessions] == [1, 1]


async def test_phase4_budget_route_delegates_to_commercial_contract() -> None:
    commercial = FakeCommercial()
    client, _, sessions = build_client(commercial=commercial)
    async with client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/budgets",
            json={"legal_entity_id": str(ENTITY_ID), "total_amount": "250000.00"},
        )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert commercial.calls[0].project_id == PROJECT_ID
    assert commercial.calls[0].legal_entity_id == ENTITY_ID
    assert sessions.sessions[0].commits == 1


async def test_phase5_site_diary_route_minimises_visitor_data_and_delegates() -> None:
    construction = FakeConstruction()
    client, _, sessions = build_client(construction=construction)
    client_record_id = uuid4()
    async with client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/site-diary",
            json={
                "entry_date": "2026-08-17",
                "client_record_id": str(client_record_id),
                "labour_strength": {"synthetic_trade": 4},
                "visitor_count": 2,
            },
        )
    assert response.status_code == 201
    assert response.json()["client_record_id"] == str(client_record_id)
    assert construction.calls[0].visitor_count == 2
    assert not hasattr(construction.calls[0], "visitor_names")
    assert sessions.sessions[0].commits == 1


async def test_phase6_bim_route_accepts_document_id_not_storage_reference() -> None:
    controls = FakeProjectControls()
    client, _, sessions = build_client(project_controls=controls)
    source_document_id = uuid4()
    async with client:
        accepted = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/bim-imports",
            json={"source_document_id": str(source_document_id)},
        )
        rejected = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/bim-imports",
            json={"source_file_reference": "https://example.invalid/model.ifc"},
        )
    assert accepted.status_code == 201
    assert accepted.json()["source_document_id"] == str(source_document_id)
    assert controls.calls[0].source_document_id == source_document_id
    assert rejected.status_code == 422
    assert sessions.sessions[0].commits == 1


async def test_phase7_change_route_is_thin_and_rejects_unknown_fields() -> None:
    changes = FakeChangeControl()
    client, _, sessions = build_client(change_control=changes)
    evidence_id = uuid4()
    async with client:
        accepted = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/change-requests",
            json={
                "description": "Synthetic change",
                "budget_impact": "100.00",
                "evidence_document_id": str(evidence_id),
            },
        )
        rejected = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/change-requests",
            json={"description": "Synthetic", "public_evidence_url": "https://example.invalid"},
        )
    assert accepted.status_code == 201
    assert changes.calls[0].evidence_document_id == evidence_id
    assert rejected.status_code == 422
    assert sessions.sessions[0].commits == 1


async def test_phase8_booking_route_accepts_ids_and_rejects_embedded_pii() -> None:
    lifecycle = FakeCustomerLifecycle()
    client, _, sessions = build_client(customer_lifecycle=lifecycle)
    customer_id, unit_id, document_id = uuid4(), uuid4(), uuid4()
    async with client:
        accepted = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/bookings",
            json={
                "customer_id": str(customer_id),
                "unit_id": str(unit_id),
                "booking_date": "2026-08-17",
                "booking_document_id": str(document_id),
            },
        )
        rejected = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/bookings",
            json={
                "customer_id": str(customer_id),
                "unit_id": str(unit_id),
                "booking_date": "2026-08-17",
                "bank_account": "SYNTHETIC-DO-NOT-STORE",
            },
        )
    assert accepted.status_code == 201
    assert lifecycle.calls[0].booking_document_id == document_id
    assert rejected.status_code == 422
    assert sessions.sessions[0].commits == 1


async def test_health_and_readiness_do_not_expose_configuration() -> None:
    client, _, _ = build_client()
    async with client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert "database" not in ready.text.lower()


async def test_readiness_failure_is_safe() -> None:
    client, _, _ = build_client(engine=FakeEngine(ready=False))
    async with client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"
    assert "synthetic" not in response.text


async def test_factory_can_dispose_an_owned_engine() -> None:
    engine = FakeEngine()
    app = create_app(
        engine=engine,  # type: ignore[arg-type]
        session_factory=FakeSessionFactory(),  # type: ignore[arg-type]
        identity_service=FakeIdentity(),  # type: ignore[arg-type]
        organization_service=FakeOrganization(),
        relying_party=RelyingParty(
            rp_id="localhost", rp_name="Atlas Test", origin="http://localhost"
        ),
        dispose_engine=True,
    )
    async with app.router.lifespan_context(app):
        assert not engine.disposed
    assert engine.disposed


def test_default_factory_requires_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ATLAS_DATABASE_URL"):
        application.create_default_app()


def test_default_factory_wires_the_environment_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    engine = FakeEngine()
    factory = FakeSessionFactory()
    seen: list[str] = []

    def fake_create_engine(url: str) -> FakeEngine:
        seen.append(url)
        return engine

    monkeypatch.setenv("ATLAS_DATABASE_URL", "postgresql+asyncpg://localhost/atlas")
    monkeypatch.setenv("ATLAS_WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setenv("ATLAS_WEBAUTHN_ORIGIN", "http://localhost")
    monkeypatch.setenv("ATLAS_DOCUMENT_STORAGE_ROOT", str(tmp_path / "documents"))
    monkeypatch.setattr(application, "create_engine", fake_create_engine)
    monkeypatch.setattr(application, "create_session_factory", lambda value: factory)
    app = application.create_default_app()
    assert app.title == "Atlas API"
    assert seen == ["postgresql+asyncpg://localhost/atlas"]


@pytest.mark.parametrize("header", [None, "Basic credentials"])
async def test_project_routes_require_an_active_opaque_session(header: str | None) -> None:
    client, _, _ = build_client()
    if header is None:
        client.headers.pop("Authorization")
    else:
        client.headers["Authorization"] = header
    async with client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_unknown_bearer_token_is_rejected() -> None:
    client, _, _ = build_client(identity=FakeIdentity(authenticated=False))
    async with client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}")
    assert response.status_code == 401


async def test_high_risk_session_is_rejected_at_the_common_boundary() -> None:
    client, _, _ = build_client(identity=FakeIdentity(risk_score=51))
    async with client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}")
    assert response.status_code == 401


async def test_get_and_list_projects_pass_the_authenticated_actor() -> None:
    client, organization, sessions = build_client()
    async with client:
        fetched = await client.get(f"/api/v1/projects/{PROJECT_ID}")
        listed = await client.get(f"/api/v1/legal-entities/{ENTITY_ID}/projects")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(PROJECT_ID)
    assert listed.json()[0]["code"] == "SYN-001"
    assert organization.calls == [
        ("get", ACTOR_ID, PROJECT_ID),
        ("list", ACTOR_ID, ENTITY_ID),
    ]
    assert [session.commits for session in sessions.sessions] == [1, 1]


async def test_create_update_and_archive_are_thin_contract_calls() -> None:
    client, organization, _ = build_client()
    async with client:
        created = await client.post(
            f"/api/v1/legal-entities/{ENTITY_ID}/projects",
            json={"name": "Synthetic Heights", "code": "SYN-001", "city": "Test City"},
        )
        updated = await client.patch(f"/api/v1/projects/{PROJECT_ID}", json={"status": "active"})
        archived = await client.post(f"/api/v1/projects/{PROJECT_ID}/archive")
    assert created.status_code == 201
    assert updated.json()["version"] == 2
    assert archived.json()["archived_at"] is not None
    assert project(archived=True).is_archived
    assert [call[0] for call in organization.calls] == ["create", "update", "archive"]
    create_data = organization.calls[0][2]
    update_data = organization.calls[1][2]
    assert isinstance(create_data, ProjectCreate)
    assert create_data.legal_entity_id == ENTITY_ID
    assert isinstance(update_data, ProjectUpdate)
    assert update_data.status == "active"


@pytest.mark.parametrize(
    ("failure", "status_code", "code"),
    [
        (NotAuthorisedError(), 403, "forbidden"),
        (NotFoundError("project does not exist"), 404, "not_found"),
        (ConflictError("project code already exists"), 409, "conflict"),
    ],
)
async def test_service_refusals_have_consistent_http_errors(
    failure: Exception, status_code: int, code: str
) -> None:
    organization = FakeOrganization()
    organization.failure = failure
    client, _, sessions = build_client(organization=organization)
    async with client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}")
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert sessions.sessions[0].rollbacks == 1


async def test_request_validation_uses_the_error_envelope() -> None:
    client, _, _ = build_client()
    async with client:
        response = await client.post(
            f"/api/v1/legal-entities/{ENTITY_ID}/projects",
            json={"name": "", "code": "SYN-001", "unexpected": True},
        )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert len(body["details"]) == 2


async def test_webauthn_registration_routes_return_browser_options_and_pending_device() -> None:
    client, _, sessions = build_client()
    client.headers.pop("Authorization")
    async with client:
        options = await client.post(
            "/api/v1/auth/webauthn/registration/options",
            json={"user_id": str(ACTOR_ID)},
        )
        verified = await client.post(
            "/api/v1/auth/webauthn/registration/verify",
            json={
                "ceremony_id": str(PROJECT_ID),
                "credential": {"id": "synthetic-credential"},
                "device_name": "Synthetic laptop",
            },
        )
    assert options.status_code == 200
    assert options.json()["public_key"]["rp"]["id"] == "localhost"
    assert verified.status_code == 200
    assert verified.json() == {
        "device_id": str(PROJECT_ID),
        "status": "pending_approval",
    }
    assert [session.commits for session in sessions.sessions] == [1, 1]


async def test_webauthn_authentication_returns_only_a_new_opaque_session_token() -> None:
    client, _, _ = build_client()
    client.headers.pop("Authorization")
    async with client:
        options = await client.post("/api/v1/auth/webauthn/authentication/options")
        verified = await client.post(
            "/api/v1/auth/webauthn/authentication/verify",
            json={
                "ceremony_id": str(PROJECT_ID),
                "credential": {"id": "synthetic-credential"},
            },
        )
    assert options.json()["public_key"]["rpId"] == "localhost"
    assert verified.status_code == 200
    assert verified.json()["session_token"] == "synthetic-opaque-token"  # noqa: S105
    assert verified.json()["token_type"] == "bearer"  # noqa: S105
    assert "jwt" not in verified.text.lower()


async def test_invalid_or_cloned_webauthn_assertions_have_safe_failures() -> None:
    identity = FakeIdentity()
    identity.ceremony_failure = InvalidCeremonyError("sensitive diagnostic")
    client, _, sessions = build_client(identity=identity)
    async with client:
        invalid = await client.post(
            "/api/v1/auth/webauthn/authentication/verify",
            json={"ceremony_id": str(PROJECT_ID), "credential": {}},
        )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "authentication_failed"
    assert "sensitive" not in invalid.text
    assert sessions.sessions[0].commits == 1

    identity = FakeIdentity()
    identity.clone_detected = True
    client, _, sessions = build_client(identity=identity)
    async with client:
        cloned = await client.post(
            "/api/v1/auth/webauthn/authentication/verify",
            json={"ceremony_id": str(PROJECT_ID), "credential": {}},
        )
    assert cloned.status_code == 401
    assert "session_token" not in cloned.text
    assert sessions.sessions[0].commits == 1


async def test_document_registry_and_revision_routes_are_thin_contract_calls() -> None:
    documents = FakeDocuments()
    client, _, _ = build_client(documents=documents)
    checksum = "a" * 64
    async with client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/documents",
            json={
                "discipline": "architectural",
                "drawing_number": "SYN-A-001",
                "document_type": "drawing",
                "classification": "confidential",
            },
        )
        revision = await client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/revisions",
            json={
                "revision_code": "A",
                "object_storage_key": "synthetic/project/document/revision-a.pdf",
                "checksum_sha256": checksum,
            },
        )
        listed = await client.get(f"/api/v1/projects/{PROJECT_ID}/documents")
        archived = await client.post(f"/api/v1/documents/{DOCUMENT_ID}/archive")
    assert created.status_code == 201
    assert revision.status_code == 201
    assert revision.json()["checksum_sha256"] == checksum
    assert listed.json()[0]["drawing_number"] == "SYN-A-001"
    assert archived.json()["version"] == 2
    assert [call[0] for call in documents.calls] == [
        "create_document",
        "add_revision",
        "list_documents",
        "archive_document",
    ]


@pytest.mark.parametrize(
    "storage_key",
    ["/etc/synthetic", "../synthetic", "https://example.invalid/object"],
)
async def test_revision_rejects_paths_and_urls(storage_key: str) -> None:
    client, _, _ = build_client()
    async with client:
        response = await client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/revisions",
            json={
                "revision_code": "A",
                "object_storage_key": storage_key,
                "checksum_sha256": "a" * 64,
            },
        )
    assert response.status_code == 422


async def test_document_conflicts_use_the_shared_error_envelope() -> None:
    documents = FakeDocuments()
    documents.failure = DocumentConflictError("synthetic revision conflict")
    client, _, sessions = build_client(documents=documents)
    async with client:
        response = await client.get(f"/api/v1/documents/{DOCUMENT_ID}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert sessions.sessions[0].rollbacks == 1


async def test_document_export_requires_fresh_step_up() -> None:
    client, _, _ = build_client()
    async with client:
        refused = await client.post(
            f"/api/v1/document-revisions/{REVISION_ID}/export-requests",
            json={"reason": "Synthetic controlled export"},
        )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"

    client, _, _ = build_client(identity=FakeIdentity(step_up=True))
    async with client:
        created = await client.post(
            f"/api/v1/document-revisions/{REVISION_ID}/export-requests",
            json={"reason": "Synthetic controlled export"},
        )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"


async def test_preview_response_is_non_cacheable_and_sandboxed() -> None:
    client, _, _ = build_client()
    async with client:
        response = await client.get("/api/v1/document-previews/synthetic-preview-token")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_binary_revision_intake_and_approved_export_are_controlled() -> None:
    client, _, _ = build_client(identity=FakeIdentity(step_up=True))
    async with client:
        uploaded = await client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/revision-content",
            params={"revision_code": "B", "issue_purpose": "Synthetic coordination"},
            content=b"%PDF-1.7 synthetic",
            headers={"Content-Type": "application/pdf"},
        )
        downloaded = await client.get(f"/api/v1/document-export-requests/{REVISION_ID}/content")
    assert uploaded.status_code == 201
    assert uploaded.json()["revision_code"] == "B"
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store, private"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["x-content-type-options"] == "nosniff"
