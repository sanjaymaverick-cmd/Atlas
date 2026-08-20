"""Baseline: apply db/schema.sql.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-17

This is the point where db/schema.sql stops being a document and becomes an
applied, versioned database. It executes the file verbatim rather than
restating its DDL in Python: the schema's behaviour lives in PL/pgSQL triggers
(the audit hash chain, append-only enforcement, the updated_at auto-attach DO
block) that would be lossy to express through Alembic operations, and a
transcription is a second source of truth waiting to drift.

**The freeze rule this docstring used to declare has been replaced (2026-08-18);
see below.** It said: from this revision onward db/schema.sql is frozen, and
schema changes are new Alembic revisions. It was never followed. Every phase
from 2 onward edited the file anyway while its migration claimed to add the
same objects, which is what eventually left `alembic upgrade head` unable to
provision a database at all. A rule with no enforcement recorded three
ratified-sounding exceptions and zero actual compliance.

**The rule now is an invariant, not a promise.** db/schema.sql stays the
readable, annotated description of the whole data model (Blueprint §6) and this
revision still applies it. Every future schema change must land in *both*
places: real DDL in a new Alembic revision, and the matching edit to
db/schema.sql. Nothing is frozen, because freezing is what failed.

What keeps the two honest is tests/integration/test_migration_schema_equivalence
.py, which provisions two databases from empty — one through the migration
chain, one from db/schema.sql — and fails if the resulting schemas differ. CI
runs it by name. Drift is now a red build rather than something discovered
years later by an operator who cannot deploy.

Revisions 0002-0012 are deliberate no-ops: db/schema.sql already carried the
full end-state schema for all 11 phases, so this baseline creates everything
and those revisions have nothing left to do. That is a one-time consequence of
the old rule's failure, not a pattern to copy — a genuine schema change from
here on needs genuine DDL in its revision, and the equivalence test will fail
if it is missing.

Downgrade drops every schema it creates. That is correct for a baseline and
catastrophic anywhere else, so it refuses to run unless ATLAS_ALLOW_DESTRUCTIVE
_DOWNGRADE is set.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"

# Every schema db/schema.sql creates, for the downgrade path.
SCHEMAS = (
    "identity organization land compliance documents design quantities budget "
    "procurement contracts construction quality inventory sales customers finance "
    "workflow communications ai audit vendor_onboarding reporting"
).split()


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into individually executable statements.

    ATLAS_DATABASE_URL uses the asyncpg driver, which executes each statement
    as a prepared statement and therefore cannot run a script containing more
    than one command (`cannot insert multiple commands into a prepared
    statement`) — unlike a synchronous driver using the simple query protocol.
    db/schema.sql must run under asyncpg, so it is split into individual
    top-level statements here rather than executed as one string.

    Splits on semicolons, but not those inside a single-quoted string literal,
    inside a `--` line comment, or inside a `$$...$$` dollar-quoted body (used
    by this file's PL/pgSQL function and DO-block definitions, whose BEGIN/END
    bodies contain semicolons that are not statement terminators).
    """
    statements = []
    current: list[str] = []
    in_single_quote = False
    in_dollar_quote = False
    in_line_comment = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_dollar_quote:
            if sql.startswith("$$", i):
                in_dollar_quote = False
                current.append("$$")
                i += 2
                continue
            current.append(ch)
            i += 1
            continue
        if in_single_quote:
            current.append(ch)
            if ch == "'":
                in_single_quote = False
            i += 1
            continue
        if sql.startswith("--", i):
            in_line_comment = True
            current.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single_quote = True
            current.append(ch)
            i += 1
            continue
        if sql.startswith("$$", i):
            in_dollar_quote = True
            current.append("$$")
            i += 2
            continue
        if ch == ";":
            current.append(ch)
            statement = "".join(current).strip()
            current = []
            i += 1
            if statement and not all(
                line.strip() == "" or line.strip().startswith("--")
                for line in statement.splitlines()
            ):
                statements.append(statement)
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail and not all(
        line.strip() == "" or line.strip().startswith("--") for line in tail.splitlines()
    ):
        statements.append(tail)
    return statements


def upgrade() -> None:
    if not SCHEMA_SQL.exists():  # pragma: no cover - defensive
        raise RuntimeError(f"canonical schema not found at {SCHEMA_SQL}")
    for statement in _split_sql_statements(SCHEMA_SQL.read_text(encoding="utf-8")):
        op.execute(statement)


def downgrade() -> None:
    if not os.environ.get("ATLAS_ALLOW_DESTRUCTIVE_DOWNGRADE"):
        raise RuntimeError(
            "Downgrading the baseline drops every Atlas schema and all data in "
            "them, including the audit log, which is append-only precisely so "
            "that it cannot be discarded. Set ATLAS_ALLOW_DESTRUCTIVE_DOWNGRADE=1 "
            "if that is genuinely what you intend."
        )
    for schema in SCHEMAS:
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
