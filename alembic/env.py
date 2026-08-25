"""Alembic environment.

The database URL comes from ``ATLAS_DATABASE_URL`` rather than alembic.ini, so
credentials are never committed (Blueprint §3.3, §15.1). Once a real secrets
backend closes §25 item 2, this reads through ``SecretsProvider`` instead.

Autogenerate is deliberately not wired up. ``db/schema.sql`` is the canonical
DDL and the schema's behaviour lives in triggers, sequences and CHECK
constraints that Alembic's model comparison cannot see. Migrations here are
written by hand.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config

_url = os.environ.get("ATLAS_DATABASE_URL")
if not _url:
    raise RuntimeError(
        "ATLAS_DATABASE_URL is not set. Alembic reads the database URL from the "
        "environment rather than alembic.ini so credentials are not committed."
    )
config.set_main_option("sqlalchemy.url", _url)

# No target_metadata: see the note on autogenerate above.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # ATLAS_DATABASE_URL uses the async asyncpg driver (see README), so the
    # engine must be async too; a sync engine_from_config engine cannot consume
    # an asyncpg URL. Alembic's own migration runner is sync, so the connection
    # is bridged in with run_sync, per Alembic's documented async recipe.
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
