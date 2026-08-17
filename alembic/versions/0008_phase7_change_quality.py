"""Add Phase 7 change, RFI, NCR, and discrepancy integrity.

Revision ID: 0008_phase7_change_quality
Revises: 0007_phase6_project_controls
"""

from __future__ import annotations

from alembic import op

revision = "0008_phase7_change_quality"
down_revision = "0007_phase6_project_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE construction.change_requests
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
      ADD COLUMN requested_by UUID REFERENCES identity.users(id),
      ADD COLUMN decided_by UUID REFERENCES identity.users(id),
      ADD COLUMN decided_at TIMESTAMPTZ,
      ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ,
      ADD CONSTRAINT chk_change_budget_impact CHECK (budget_impact IS NULL OR budget_impact >= 0);
    ALTER TABLE quality.rfis
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
      ADD COLUMN responded_by UUID REFERENCES identity.users(id),
      ADD COLUMN responded_at TIMESTAMPTZ,
      ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE quality.ncrs
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
      ADD COLUMN closed_by UUID REFERENCES identity.users(id),
      ADD COLUMN closed_at TIMESTAMPTZ,
      ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE quality.discrepancy_cases
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
      ADD COLUMN resolved_by UUID REFERENCES identity.users(id),
      ADD COLUMN resolved_at TIMESTAMPTZ,
      ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE quantities.quantity_items
      ADD CONSTRAINT uq_quantity_item_id_project UNIQUE (id, project_id);
    ALTER TABLE construction.schedule_activities
      ADD CONSTRAINT uq_schedule_activity_id_project UNIQUE (id, project_id);
    ALTER TABLE quality.inspections
      ADD CONSTRAINT uq_inspection_id_project UNIQUE (id, project_id);
    ALTER TABLE quality.ncrs
      DROP CONSTRAINT ncrs_inspection_id_fkey,
      DROP CONSTRAINT ncrs_schedule_activity_id_fkey,
      DROP CONSTRAINT ncrs_reinspection_id_fkey,
      ADD CONSTRAINT fk_ncr_inspection_project FOREIGN KEY (inspection_id, project_id)
        REFERENCES quality.inspections(id, project_id),
      ADD CONSTRAINT fk_ncr_activity_project FOREIGN KEY (schedule_activity_id, project_id)
        REFERENCES construction.schedule_activities(id, project_id),
      ADD CONSTRAINT fk_ncr_reinspection_project FOREIGN KEY (reinspection_id, project_id)
        REFERENCES quality.inspections(id, project_id);
    ALTER TABLE quality.discrepancy_cases
      DROP CONSTRAINT discrepancy_cases_quantity_item_id_fkey,
      ADD CONSTRAINT fk_discrepancy_quantity_project FOREIGN KEY (quantity_item_id, project_id)
        REFERENCES quantities.quantity_items(id, project_id);
    CREATE INDEX idx_change_requests_project_status
      ON construction.change_requests(project_id,status);
    CREATE INDEX idx_discrepancy_cases_project_status
      ON quality.discrepancy_cases(project_id,status);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX quality.idx_discrepancy_cases_project_status;
    DROP INDEX construction.idx_change_requests_project_status;
    ALTER TABLE quality.discrepancy_cases
      DROP CONSTRAINT fk_discrepancy_quantity_project,
      ADD CONSTRAINT discrepancy_cases_quantity_item_id_fkey FOREIGN KEY (quantity_item_id)
        REFERENCES quantities.quantity_items(id);
    ALTER TABLE quality.ncrs
      DROP CONSTRAINT fk_ncr_inspection_project,
      DROP CONSTRAINT fk_ncr_activity_project,
      DROP CONSTRAINT fk_ncr_reinspection_project,
      ADD CONSTRAINT ncrs_inspection_id_fkey FOREIGN KEY (inspection_id)
        REFERENCES quality.inspections(id),
      ADD CONSTRAINT ncrs_schedule_activity_id_fkey FOREIGN KEY (schedule_activity_id)
        REFERENCES construction.schedule_activities(id),
      ADD CONSTRAINT ncrs_reinspection_id_fkey FOREIGN KEY (reinspection_id)
        REFERENCES quality.inspections(id);
    ALTER TABLE quality.inspections DROP CONSTRAINT uq_inspection_id_project;
    ALTER TABLE construction.schedule_activities
      DROP CONSTRAINT uq_schedule_activity_id_project;
    ALTER TABLE quantities.quantity_items DROP CONSTRAINT uq_quantity_item_id_project;
    ALTER TABLE quality.discrepancy_cases
      DROP COLUMN evidence_document_id, DROP COLUMN resolved_by, DROP COLUMN resolved_at,
      DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE quality.ncrs
      DROP COLUMN evidence_document_id, DROP COLUMN closed_by, DROP COLUMN closed_at,
      DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE quality.rfis
      DROP COLUMN evidence_document_id, DROP COLUMN responded_by, DROP COLUMN responded_at,
      DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE construction.change_requests
      DROP CONSTRAINT chk_change_budget_impact,
      DROP COLUMN evidence_document_id, DROP COLUMN requested_by, DROP COLUMN decided_by,
      DROP COLUMN decided_at, DROP COLUMN created_by, DROP COLUMN updated_by,
      DROP COLUMN version, DROP COLUMN archived_at;
    """)
