"""Add provider-neutral Phase 11 AI safety boundaries.

Revision ID: 0012_phase11_ai_safety
Revises: 0011_phase10_reporting

No-op. `db/schema.sql` already carries this schema state (all 11 phases); see
`0003_document_versioning` for the full rationale. `0001_baseline` remains the
sole owner; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0012_phase11_ai_safety"
down_revision = "0011_phase10_reporting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
