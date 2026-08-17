"""Add Phase 5 construction, offline diary, QA/QC, snag, and EHS integrity.

Revision ID: 0006_phase5_construction_quality
Revises: 0005_phase4_commercial_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0006_phase5_construction_quality"
down_revision = "0005_phase4_commercial_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE construction.schedule_activities
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT chk_schedule_planned_dates
            CHECK (planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start),
          ADD CONSTRAINT chk_schedule_actual_dates
            CHECK (actual_end IS NULL OR actual_start IS NULL OR actual_end >= actual_start);
        ALTER TABLE construction.site_diary_entries
          ADD COLUMN client_record_id UUID NOT NULL DEFAULT gen_random_uuid(),
          ADD COLUMN device_recorded_at TIMESTAMPTZ,
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT uq_site_diary_client_record UNIQUE (project_id, client_record_id);
        ALTER TABLE construction.ehs_incidents
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;
        ALTER TABLE quality.inspection_templates
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT uq_inspection_template_project_name UNIQUE (project_id, template_name);
        ALTER TABLE quality.inspections
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;

        CREATE TABLE construction.progress_updates (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES organization.projects(id),
          schedule_activity_id UUID NOT NULL REFERENCES construction.schedule_activities(id),
          progress_date DATE NOT NULL,
          percent_complete NUMERIC(5,2) NOT NULL CHECK (percent_complete BETWEEN 0 AND 100),
          notes TEXT,
          evidence_document_id UUID REFERENCES documents.documents(id),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID REFERENCES identity.users(id),
          updated_by UUID REFERENCES identity.users(id),
          version INTEGER NOT NULL DEFAULT 1,
          archived_at TIMESTAMPTZ,
          UNIQUE (schedule_activity_id, progress_date)
        );
        CREATE TABLE quality.inspection_evidence (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          inspection_id UUID NOT NULL REFERENCES quality.inspections(id),
          document_id UUID NOT NULL REFERENCES documents.documents(id),
          evidence_type TEXT NOT NULL DEFAULT 'photo'
            CHECK (evidence_type IN ('photo','report','certificate','other')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID REFERENCES identity.users(id),
          UNIQUE (inspection_id, document_id)
        );
        CREATE TABLE quality.snag_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES organization.projects(id),
          inspection_id UUID REFERENCES quality.inspections(id),
          building_id UUID REFERENCES organization.buildings(id),
          floor_id UUID REFERENCES organization.floors(id),
          unit_id UUID REFERENCES organization.units(id),
          description TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'minor'
            CHECK (severity IN ('minor','major','critical')),
          assigned_to UUID REFERENCES identity.users(id),
          due_date DATE,
          evidence_document_id UUID REFERENCES documents.documents(id),
          status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open','assigned','rectified','verified','closed')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID REFERENCES identity.users(id),
          updated_by UUID REFERENCES identity.users(id),
          version INTEGER NOT NULL DEFAULT 1,
          archived_at TIMESTAMPTZ
        );
        CREATE INDEX idx_progress_updates_project_date
          ON construction.progress_updates(project_id, progress_date);
        CREATE INDEX idx_snag_items_project_status
          ON quality.snag_items(project_id, status);
        CREATE TRIGGER trg_set_updated_at
          BEFORE UPDATE ON construction.site_diary_entries
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER trg_set_updated_at
          BEFORE UPDATE ON construction.progress_updates
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER trg_set_updated_at
          BEFORE UPDATE ON quality.snag_items
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE quality.snag_items;
        DROP TABLE quality.inspection_evidence;
        DROP TABLE construction.progress_updates;
        DROP TRIGGER trg_set_updated_at ON construction.site_diary_entries;
        ALTER TABLE quality.inspections
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE quality.inspection_templates
          DROP CONSTRAINT uq_inspection_template_project_name,
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE construction.ehs_incidents
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE construction.site_diary_entries
          DROP CONSTRAINT uq_site_diary_client_record,
          DROP COLUMN client_record_id, DROP COLUMN device_recorded_at,
          DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE construction.schedule_activities
          DROP CONSTRAINT chk_schedule_planned_dates,
          DROP CONSTRAINT chk_schedule_actual_dates,
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        """
    )
