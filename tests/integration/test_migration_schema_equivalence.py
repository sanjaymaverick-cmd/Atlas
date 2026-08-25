"""The migration chain and ``db/schema.sql`` must describe the same database.

Atlas keeps two descriptions of its schema: ``db/schema.sql``, the readable
annotated canonical DDL the blueprint refers to, and the Alembic revisions,
which are the only thing that can change a database that already holds data.
Two descriptions of one schema is a drift problem waiting to happen, and it
has already happened once: every phase from 2 onward edited ``db/schema.sql``
while its migration claimed to add the same objects, until
``alembic upgrade head`` could not provision a database at all.

This test replaces that freeze rule with an invariant a machine can check.
It provisions two disposable databases from empty — one by running the
migration chain, one by applying ``db/schema.sql`` directly — and asserts the
resulting schemas are identical. A future change must therefore land in both
places or fail here.

``alembic_version`` is excluded: it is bookkeeping the migration path creates
and the direct path legitimately does not have.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"

pytestmark = pytest.mark.integration

# Disposable, and dropped again in the finally block. Named distinctly so a
# stray one is obviously not the developer's own test database.
MIGRATED_DB = "atlas_equivalence_migrated"
DECLARED_DB = "atlas_equivalence_declared"


def _with_database(url: str, name: str) -> str:
    """Point a connection URL at a different database, preserving everything else.

    Rewrites only the path, so this works both for TCP URLs and for the
    socket-directory form (``...?host=/tmp&port=55432``) that the rootless
    local setup in docs/local-postgres.md produces.
    """
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


def _async_url(url: str) -> str:
    """Alembic reads ATLAS_DATABASE_URL, which is documented as an asyncpg URL."""
    parts = urlsplit(url)
    if parts.scheme == "postgresql":
        parts = parts._replace(scheme="postgresql+asyncpg")
    return urlunsplit(parts)


def _run(command: list[str], **extra_env: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
            env={**os.environ, **extra_env},
        )
    except FileNotFoundError:  # pragma: no cover - environment problem
        pytest.fail(
            f"{command[0]} is not on PATH. This test provisions real databases; "
            "see docs/local-postgres.md."
        )


def _psql(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["psql", url, "-v", "ON_ERROR_STOP=1", "-q", *args])


def _recreate(admin_url: str, name: str) -> None:
    for statement in (f'DROP DATABASE IF EXISTS "{name}"', f'CREATE DATABASE "{name}"'):
        result = _psql(admin_url, "-c", statement)
        if result.returncode != 0:  # pragma: no cover - defensive
            pytest.fail(f"{statement} failed:\n{result.stderr}{result.stdout}")


def _drop(admin_url: str, name: str) -> None:
    _psql(admin_url, "-c", f'DROP DATABASE IF EXISTS "{name}"')


def _schema_dump(url: str) -> str:
    """A normalised structural dump: no ownership, comments, or blank lines."""
    result = _run(
        [
            "pg_dump",
            url,
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--no-comments",
            "--exclude-table=public.alembic_version",
        ]
    )
    if result.returncode != 0:  # pragma: no cover - defensive
        pytest.fail(f"pg_dump failed:\n{result.stderr}{result.stdout}")
    lines = (line.rstrip() for line in result.stdout.splitlines())
    return "\n".join(
        line
        for line in lines
        # \restrict and \unrestrict wrap the dump and carry a fresh random
        # token on every pg_dump invocation, so they differ between two dumps
        # of the same schema and say nothing about its structure.
        if line
        and not line.startswith("--")
        and not line.startswith(("\\restrict", "\\unrestrict"))
    )


def test_migration_chain_and_schema_sql_describe_the_same_database(
    database_url: str,
) -> None:
    admin_url = _with_database(database_url, "postgres")
    migrated_url = _with_database(database_url, MIGRATED_DB)
    declared_url = _with_database(database_url, DECLARED_DB)

    _recreate(admin_url, MIGRATED_DB)
    _recreate(admin_url, DECLARED_DB)
    try:
        # Invoked through this interpreter rather than a bare `alembic` so the
        # test uses the same environment pytest is running in, whatever PATH says.
        migration = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            ATLAS_DATABASE_URL=_async_url(migrated_url),
        )
        if migration.returncode != 0:
            pytest.fail(
                "`alembic upgrade head` could not provision a database from "
                f"empty:\n{migration.stderr}{migration.stdout}"
            )

        declaration = _psql(declared_url, "-f", str(SCHEMA_SQL))
        if declaration.returncode != 0:
            pytest.fail(
                "db/schema.sql could not be applied to an empty database:\n"
                f"{declaration.stderr}{declaration.stdout}"
            )

        migrated = _schema_dump(migrated_url)
        declared = _schema_dump(declared_url)
        if migrated != declared:
            diff = "\n".join(
                difflib.unified_diff(
                    declared.splitlines(),
                    migrated.splitlines(),
                    fromfile="db/schema.sql applied directly",
                    tofile="alembic upgrade head",
                    lineterm="",
                )
            )
            pytest.fail(
                "The migration chain and db/schema.sql no longer describe the "
                "same database. A schema change must land in both: add the "
                "migration DDL and make the matching edit to db/schema.sql.\n\n"
                f"{diff}"
            )
    finally:
        _drop(admin_url, MIGRATED_DB)
        _drop(admin_url, DECLARED_DB)
