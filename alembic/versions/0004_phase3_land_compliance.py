"""Strengthen Phase 3 land, finance, and compliance records.

Revision ID: 0004_phase3_land_compliance
Revises: 0003_document_versioning

No-op. `db/schema.sql` already carries this schema state (all 11 phases); see
`0003_document_versioning` for the full rationale. `0001_baseline` remains the
sole owner; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0004_phase3_land_compliance"
down_revision = "0003_document_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
