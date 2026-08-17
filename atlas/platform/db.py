"""Database engine and session management.

One async engine and one session factory for the whole modular monolith
(Blueprint §7). Modules receive a session; they do not create engines.

The base class carries no metadata conventions that would tempt Alembic into
autogenerating DDL. ``db/schema.sql`` and the Alembic revisions after it are
the canonical schema; the mappings below describe it, they do not define it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for hand-written mappings onto the canonical schema."""


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build the async engine.

    ``pool_pre_ping`` is on because this is a self-hosted deployment where the
    database may be restarted underneath a long-lived application process
    (Blueprint §21, "graceful recovery after power failure"); a stale pooled
    connection should be discovered and replaced rather than surfacing as a
    request failure.
    """
    return create_async_engine(url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the session factory.

    ``expire_on_commit=False`` so objects stay readable after commit — the
    audit writer records an after-state from the same objects the caller just
    committed, and re-fetching them would be a wasted round trip.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Run a unit of work in one transaction.

    A mutation and its audit event must commit or fail together: an audit log
    missing an event that happened is as bad as one containing an event that
    did not. Callers get one session and one transaction boundary rather than
    committing per statement.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
