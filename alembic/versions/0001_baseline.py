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

**From this revision onward, db/schema.sql is frozen.** Schema changes are new
Alembic revisions. The file stays in the repository as the readable, annotated
description of the whole data model — Blueprint §6 — and remains what a fresh
Phase-1 database is built from, but it is no longer edited in place.

One ratified exception exists, recorded here because this docstring is where the
freeze is declared and a reader who sees only the rule would be misled. On
2026-08-18 the owner approved commit b990bdc, which reordered db/schema.sql so
the documents section precedes land. Grounds: as committed the file referenced
documents.documents before that schema existed, so it could not be applied to an
empty database and this migration could not run at all. The change is a pure
relocation — sorted contents identical before and after — so no statement
changed and no provisioned database diverges. The exception covers that
reordering only; the freeze otherwise stands. See
docs/production-readiness-todo.md, where enforcement of the rule is still open.

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


def upgrade() -> None:
    if not SCHEMA_SQL.exists():  # pragma: no cover - defensive
        raise RuntimeError(f"canonical schema not found at {SCHEMA_SQL}")
    op.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


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
