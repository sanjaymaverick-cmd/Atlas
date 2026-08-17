"""Integration-test fixtures.

Integration tests run against a real PostgreSQL instance with ``db/schema.sql``
applied. They are not mocked: the behaviour under test — the hash-chain
trigger, the append-only triggers, the CHECK constraints — lives in the
database, and a mock would only assert that the mock behaves as written.

Set ``ATLAS_TEST_DATABASE_URL`` to point at a disposable database. When it is
unset the integration tests skip, so a developer without a database can still
run the unit suite. CI always sets it, and runs the chain-integrity test by
name so a skip there cannot be mistaken for a pass.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"


def _database_url() -> str | None:
    return os.environ.get("ATLAS_TEST_DATABASE_URL")


requires_database = pytest.mark.skipif(
    _database_url() is None,
    reason="ATLAS_TEST_DATABASE_URL is not set",
)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _database_url()
    if url is None:
        pytest.skip("ATLAS_TEST_DATABASE_URL is not set")
    return url


# Every schema db/schema.sql creates. Dropped before the file is applied so a
# session starts from a known state; schema.sql uses plain CREATE TABLE, so
# re-applying it over an existing database would otherwise fail.
_SCHEMAS = (
    "identity organization land compliance documents design quantities budget "
    "procurement contracts construction quality inventory sales customers finance "
    "workflow communications ai audit vendor_onboarding reporting"
).split()


def _psql(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["psql", database_url, "-v", "ON_ERROR_STOP=1", "-q", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def _schema_applied(database_url: str) -> None:
    """Apply db/schema.sql once per session, from a clean slate.

    Applied with psql rather than through the ORM deliberately: schema.sql is
    the canonical DDL, and running it the way an operator would is part of what
    these tests verify.
    """
    if not SCHEMA_SQL.exists():  # pragma: no cover - defensive
        pytest.fail(f"schema not found at {SCHEMA_SQL}")

    drop = ";".join(f"DROP SCHEMA IF EXISTS {s} CASCADE" for s in _SCHEMAS)
    reset = _psql(database_url, "-c", drop)
    if reset.returncode != 0:  # pragma: no cover - defensive
        pytest.fail(f"resetting schemas failed:\n{reset.stderr}{reset.stdout}")

    result = _psql(database_url, "-f", str(SCHEMA_SQL))
    if result.returncode != 0:
        pytest.fail(f"applying schema.sql failed:\n{result.stderr}{result.stdout}")


@pytest.fixture
def db(database_url: str, _schema_applied: None) -> Iterator[object]:
    """A psycopg-style connection with a clean audit table.

    Truncating the audit table between tests would normally be impossible —
    it is append-only by design — so the fixture drops and recreates the chain
    state through the owning role instead. This is a test-only affordance and
    is deliberately awkward: nothing in application code may do it.
    """
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("ALTER TABLE audit.audit_events DISABLE TRIGGER trg_audit_no_delete")
        conn.execute("DELETE FROM audit.audit_events")
        conn.execute("ALTER TABLE audit.audit_events ENABLE TRIGGER trg_audit_no_delete")
        conn.execute("ALTER SEQUENCE audit.audit_events_seq RESTART WITH 1")
        yield conn
