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

import os

from sqlalchemy import engine_from_config, pool

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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
