"""Add Phase 2 document versioning invariants.

Revision ID: 0003_document_versioning
Revises: 0002_webauthn_challenges

No-op. `db/schema.sql` already carries the full current-state schema across all
11 phases (confirmed: `documents.documents.updated_by`/`version`,
`documents.preview_grants`, `documents.export_requests`, and their constraints
are already present), and `0001_baseline` applies that file verbatim. Every
migration this table originally added was therefore already created by
`0001_baseline`, and running this revision's DDL against a freshly provisioned
database fails with "already exists" — see `docs/phase-11-resume-handoff.md`
defect C, which found the same pattern in `0002_webauthn_challenges`. Atlas has
no previously-provisioned database to preserve, so the resolution is to make
every migration after `0001_baseline` a no-op rather than reconcile each one
individually against the frozen file. `0001_baseline` remains the sole owner of
this schema state; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0003_document_versioning"
down_revision = "0002_webauthn_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
