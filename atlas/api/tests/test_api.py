"""HTTP behavior through injected module contracts and synthetic records."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from atlas.api import application
from atlas.api.application import create_app
from atlas.modules.identity.schemas import SessionContext
from atlas.modules.organization.contracts import ConflictError, NotAuthorisedError, NotFoundError
from atlas.modules.organization.schemas import ProjectCreate, ProjectSummary, ProjectUpdate
from atlas.platform.access_control import DeviceTrust

pytestmark = pytest.mark.unit

ACTOR_ID = UUID("11111111-1111-1111-1111-111111111111")
ENTITY_ID = UUID("22222222-2222-2222-2222-222222222222")
PROJECT_ID = UUID("33333333-3333-3333-3333-333333333333")


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
    def __init__(self, *, authenticated: bool = True) -> None:
        self.authenticated = authenticated
        self.tokens: list[str] = []

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
            risk_score=0,
            step_up_verified=False,
            step_up_verified_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            revoked_at=None,
        )


class FakeOrganization:
    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.calls: list[tuple[str, UUID, object]] = []

    def _raise_if_needed(self) -> None:
        if self.failure is not None:
            raise self.failure

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


def build_client(
    *,
    engine: FakeEngine | None = None,
    identity: FakeIdentity | None = None,
    organization: FakeOrganization | None = None,
) -> tuple[httpx.AsyncClient, FakeOrganization, FakeSessionFactory]:
    fake_organization = organization or FakeOrganization()
    session_factory = FakeSessionFactory()
    app = create_app(
        engine=engine or FakeEngine(),  # type: ignore[arg-type]
        session_factory=session_factory,  # type: ignore[arg-type]
        identity_service=identity or FakeIdentity(),  # type: ignore[arg-type]
        organization_service=fake_organization,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer synthetic-session-token"},
    )
    return client, fake_organization, session_factory


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
) -> None:
    engine = FakeEngine()
    factory = FakeSessionFactory()
    seen: list[str] = []

    def fake_create_engine(url: str) -> FakeEngine:
        seen.append(url)
        return engine

    monkeypatch.setenv("ATLAS_DATABASE_URL", "postgresql+asyncpg://localhost/atlas")
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
