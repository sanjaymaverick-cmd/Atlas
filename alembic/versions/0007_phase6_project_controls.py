"""Add Phase 6 BIM, quantity, WBS, and material-traceability integrity.

Revision ID: 0007_phase6_project_controls
Revises: 0006_phase5_construction_quality

No-op. `db/schema.sql` already carries this schema state (all 11 phases); see
`0003_document_versioning` for the full rationale. `0001_baseline` remains the
sole owner; this revision now only marks the chain's position.
"""

from __future__ import annotations

revision = "0007_phase6_project_controls"
down_revision = "0006_phase5_construction_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
