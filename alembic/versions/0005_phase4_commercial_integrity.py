"""Add Phase 4 commercial integrity columns and constraints.

Revision ID: 0005_phase4_commercial_integrity
Revises: 0004_phase3_land_compliance

No-op. `db/schema.sql` already carries this schema state (all 11 phases); see
`0003_document_versioning` for the full rationale. `0001_baseline` remains the
sole owner; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0005_phase4_commercial_integrity"
down_revision = "0004_phase3_land_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
