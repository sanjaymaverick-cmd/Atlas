"""Database-free branch coverage for opaque session authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from atlas.modules.identity import repository
from atlas.modules.identity.schemas import SessionContext
from atlas.modules.identity.service import IdentityService
from atlas.platform.access_control import DeviceTrust

pytestmark = pytest.mark.unit


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
