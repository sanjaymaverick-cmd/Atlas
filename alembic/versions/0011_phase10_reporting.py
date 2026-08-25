"""Add Phase 10 separated reporting summary.

Revision ID: 0011_phase10_reporting
Revises: 0010_phase9_tally_reconciliation

No-op. `db/schema.sql` already carries this schema state (all 11 phases); see
`0003_document_versioning` for the full rationale. `0001_baseline` remains the
sole owner; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0011_phase10_reporting"
down_revision = "0010_phase9_tally_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
