"""Persist one-time WebAuthn ceremony challenges.

Revision ID: 0002_webauthn_challenges
Revises: 0001_baseline

No-op. `identity.webauthn_challenges` was added to `db/schema.sql` by commit
`4e4c85d` ("Complete WebAuthn and local Phase 2 documents") after `0001_baseline`
had already declared the file frozen, so `0001_baseline` applying `db/schema.sql`
verbatim already creates this table (and its index) with the exact definition
this revision used to create. Running both against an empty database failed
with `relation "webauthn_challenges" already exists`, which meant
`alembic upgrade head` could not provision a database from empty — see
`docs/phase-11-resume-handoff.md` defect C. `0001_baseline` remains the sole
owner of this table; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0002_webauthn_challenges"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
