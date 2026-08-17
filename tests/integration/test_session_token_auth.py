"""Opaque bearer tokens resolve through Identity's published contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from atlas.modules.identity.service import IdentityService
from atlas.modules.identity.sessions import issue_token

pytestmark = pytest.mark.integration


@pytest.fixture
async def async_session(database_url: str, db: Any) -> Any:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_session(
    session: AsyncSession,
    *,
    token_hash: str,
    expires_at: datetime,
    revoked_at: datetime | None = None,
) -> None:
    user_id = uuid4()
    device_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO identity.users (id, full_name, email, status, version) "
            "VALUES (:id, 'Synthetic User', :email, 'active', 1)"
        ),
        {"id": user_id, "email": f"synthetic-{user_id}@example.invalid"},
    )
    await session.execute(
        text(
            "INSERT INTO identity.devices "
            "(id, user_id, passkey_credential_id, public_key, trust_level, status) "
            "VALUES (:id, :user_id, :credential_id, 'synthetic-key', 'trusted', 'active')"
        ),
        {"id": device_id, "user_id": user_id, "credential_id": f"synthetic-{device_id}"},
    )
    await session.execute(
        text(
            "INSERT INTO identity.sessions "
            "(user_id, device_id, session_token_hash, expires_at, revoked_at) "
            "VALUES (:user_id, :device_id, :token_hash, :expires_at, :revoked_at)"
        ),
        {
            "user_id": user_id,
            "device_id": device_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "revoked_at": revoked_at,
        },
    )
    await session.commit()


async def test_valid_token_authenticates_and_plain_token_is_not_stored(
    async_session: AsyncSession,
) -> None:
    token, token_hash = issue_token()
    await _seed_session(
        async_session,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    context = await IdentityService().authenticate_session_token(async_session, token)
    assert context is not None
    assert context.user_status == "active"
    stored = (
        await async_session.execute(text("SELECT session_token_hash FROM identity.sessions"))
    ).scalar_one()
    assert stored == token_hash
    assert token not in stored


@pytest.mark.parametrize(
    ("expires_delta", "revoked"),
    [(timedelta(seconds=-1), False), (timedelta(hours=1), True)],
)
async def test_expired_or_revoked_token_is_rejected(
    async_session: AsyncSession, expires_delta: timedelta, revoked: bool
) -> None:
    token, token_hash = issue_token()
    await _seed_session(
        async_session,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + expires_delta,
        revoked_at=datetime.now(UTC) if revoked else None,
    )
    assert await IdentityService().authenticate_session_token(async_session, token) is None
