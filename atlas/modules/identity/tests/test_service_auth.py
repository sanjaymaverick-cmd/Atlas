"""Database-free branch coverage for opaque session authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity import repository
from atlas.modules.identity import service as service_module
from atlas.modules.identity.contracts import InvalidCeremonyError
from atlas.modules.identity.models import WebAuthnChallenge
from atlas.modules.identity.schemas import RelyingParty, SessionContext
from atlas.modules.identity.service import IdentityService
from atlas.modules.identity.webauthn_adapter import AuthenticationResult, RegistrationResult
from atlas.platform.access_control import DeviceTrust

pytestmark = pytest.mark.unit

RP = RelyingParty(rp_id="localhost", rp_name="Atlas Test", origin="http://localhost")


async def ignore_audit(*args: object, **kwargs: object) -> None:
    return None


def context(
    *,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    user_status: str = "active",
    device_status: str = "active",
) -> SessionContext:
    return SessionContext(
        session_id=uuid4(),
        user_id=uuid4(),
        device_id=uuid4(),
        user_status=user_status,
        device_status=device_status,
        device_trust=DeviceTrust.STANDARD,
        risk_score=0,
        step_up_verified=False,
        step_up_verified_at=None,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
        revoked_at=revoked_at,
    )


async def test_empty_or_unknown_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = IdentityService()
    assert await identity.authenticate_session_token(object(), "") is None  # type: ignore[arg-type]

    async def not_found(session: object, token_hash: str) -> None:
        return None

    monkeypatch.setattr(repository, "get_session_by_token_hash", not_found)
    assert (
        await identity.authenticate_session_token(object(), "unknown")  # type: ignore[arg-type]
        is None
    )


@pytest.mark.parametrize(
    "session_context",
    [
        None,
        context(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        context(revoked_at=datetime.now(UTC)),
        context(user_status="suspended"),
        context(device_status="revoked"),
    ],
)
async def test_inactive_session_context_is_rejected(
    monkeypatch: pytest.MonkeyPatch, session_context: SessionContext | None
) -> None:
    identity = IdentityService()

    async def found(session: object, token_hash: str) -> SimpleNamespace:
        return SimpleNamespace(id=uuid4())

    async def get_session(session: object, session_id: object) -> SessionContext | None:
        return session_context

    monkeypatch.setattr(repository, "get_session_by_token_hash", found)
    monkeypatch.setattr(identity, "get_session", get_session)
    assert (
        await identity.authenticate_session_token(object(), "opaque")  # type: ignore[arg-type]
        is None
    )


async def test_active_session_context_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = IdentityService()
    expected = context()

    async def found(session: object, token_hash: str) -> SimpleNamespace:
        return SimpleNamespace(id=expected.session_id)

    async def get_session(session: object, session_id: object) -> SessionContext:
        return expected

    monkeypatch.setattr(repository, "get_session_by_token_hash", found)
    monkeypatch.setattr(identity, "get_session", get_session)
    assert (
        await identity.authenticate_session_token(object(), "opaque")  # type: ignore[arg-type]
        == expected
    )


class FlushSession:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


class WriteSession(FlushSession):
    def __init__(self) -> None:
        super().__init__()
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


async def test_registration_options_persist_the_generated_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityService()
    user_id = uuid4()

    async def get_user(session: object, requested_id: object) -> SimpleNamespace:
        return SimpleNamespace(
            id=user_id,
            email="synthetic@example.invalid",
            full_name="Synthetic User",
            status="active",
        )

    monkeypatch.setattr(repository, "get_user", get_user)
    monkeypatch.setattr(
        service_module,
        "registration_options",
        lambda **kwargs: (b"synthetic-challenge", {"challenge": "synthetic"}),
    )
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    session = WriteSession()
    options = await identity.begin_registration(cast(AsyncSession, session), user_id=user_id, rp=RP)
    challenge = cast(WebAuthnChallenge, session.added[0])
    assert options.ceremony_id == challenge.id
    assert challenge.user_id == user_id
    assert challenge.ceremony_type == "registration"
    assert session.flushes == 1


async def test_registration_verification_enrolls_a_pending_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityService()
    user_id = uuid4()
    challenge = cast(
        WebAuthnChallenge,
        SimpleNamespace(user_id=user_id, challenge="c3ludGhldGlj"),
    )
    expected_device_id = uuid4()

    async def consume(*args: object) -> WebAuthnChallenge:
        return challenge

    async def enroll(*args: object, **kwargs: object) -> object:
        assert kwargs["user_id"] == user_id
        assert kwargs["sign_counter"] == 4
        return expected_device_id

    monkeypatch.setattr(identity, "_consume_challenge", consume)
    monkeypatch.setattr(
        service_module,
        "verify_registration",
        lambda **kwargs: RegistrationResult("credential", "public-key", 4),
    )
    monkeypatch.setattr(service_module, "enroll_device", enroll)
    result = await identity.complete_registration(
        cast(AsyncSession, WriteSession()),
        ceremony_id=uuid4(),
        credential={"id": "synthetic"},
        device_name="Synthetic laptop",
        rp=RP,
    )
    assert result == expected_device_id


async def test_authentication_options_persist_an_unbound_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityService()
    monkeypatch.setattr(
        service_module,
        "authentication_options",
        lambda **kwargs: (b"synthetic-challenge", {"challenge": "synthetic"}),
    )
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    session = WriteSession()
    options = await identity.begin_authentication(cast(AsyncSession, session), rp=RP)
    challenge = cast(WebAuthnChallenge, session.added[0])
    assert options.ceremony_id == challenge.id
    assert challenge.user_id is None
    assert challenge.ceremony_type == "authentication"


async def test_successful_assertion_updates_device_and_issues_opaque_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = IdentityService()
    user_id = uuid4()
    device = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status="active",
        public_key="cHVibGlj",
        sign_counter=2,
        last_used_at=None,
    )
    challenge = cast(WebAuthnChallenge, SimpleNamespace(challenge="c3ludGhldGlj"))

    async def consume(*args: object) -> WebAuthnChallenge:
        return challenge

    async def get_device(*args: object) -> SimpleNamespace:
        return device

    monkeypatch.setattr(identity, "_consume_challenge", consume)
    monkeypatch.setattr(service_module, "credential_id_from_authentication", lambda value: "cred")
    monkeypatch.setattr(repository, "get_device_by_credential_id", get_device)
    monkeypatch.setattr(
        service_module,
        "verify_authentication",
        lambda **kwargs: AuthenticationResult("cred", 3),
    )
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    session = WriteSession()
    outcome = await identity.complete_authentication(
        cast(AsyncSession, session),
        ceremony_id=uuid4(),
        credential={"id": "synthetic"},
        rp=RP,
    )
    assert outcome.session_token is not None
    assert outcome.expires_at is not None
    assert not outcome.clone_detected
    assert device.sign_counter == 3
    assert len(session.added) == 1


async def test_challenge_is_consumed_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = IdentityService()
    challenge_id = uuid4()
    row = cast(
        WebAuthnChallenge,
        SimpleNamespace(
            id=challenge_id,
            user_id=None,
            ceremony_type="authentication",
            used_at=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
    )

    async def found(session: object, requested_id: object) -> WebAuthnChallenge:
        assert requested_id == challenge_id
        return row

    monkeypatch.setattr(repository, "get_challenge_for_update", found)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    session = FlushSession()
    consumed = await identity._consume_challenge(
        cast(AsyncSession, session),
        challenge_id,
        "authentication",
    )
    assert consumed is row
    assert row.used_at is not None
    assert session.flushes == 1

    with pytest.raises(InvalidCeremonyError):
        await identity._consume_challenge(
            cast(AsyncSession, session),
            challenge_id,
            "authentication",
        )


@pytest.mark.parametrize("kind", ["registration", "authentication"])
async def test_expired_or_wrong_kind_challenge_is_rejected(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    identity = IdentityService()
    row = cast(
        WebAuthnChallenge,
        SimpleNamespace(
            id=uuid4(),
            user_id=None,
            ceremony_type=kind,
            used_at=None,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )

    async def found(session: object, requested_id: object) -> WebAuthnChallenge:
        return row

    monkeypatch.setattr(repository, "get_challenge_for_update", found)
    monkeypatch.setattr(service_module, "record_event", ignore_audit)
    with pytest.raises(InvalidCeremonyError):
        await identity._consume_challenge(
            cast(AsyncSession, FlushSession()),
            uuid4(),
            "authentication" if kind == "registration" else "registration",
        )
