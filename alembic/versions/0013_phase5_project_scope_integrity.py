"""Enforce Phase 5 project-scoped references.

Revision ID: 0013_phase5_scope_integrity
Revises: 0012_phase11_ai_safety
"""

from __future__ import annotations

from alembic import op

revision = "0013_phase5_scope_integrity"
down_revision = "0012_phase11_ai_safety"
branch_labels = None
depends_on = None


def _add_constraint_if_missing(table: str, name: str, ddl: str) -> None:
    op.execute(
        f"""DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = '{name}' AND conrelid = '{table}'::regclass
          ) THEN
            ALTER TABLE {table} ADD CONSTRAINT {name} {ddl};
          END IF;
        END
        $$"""  # noqa: S608 - identifiers are module-owned migration constants
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE construction.schedule_activities "
        "DROP CONSTRAINT IF EXISTS schedule_activities_predecessor_activity_id_fkey"
    )
    op.execute(
        "ALTER TABLE construction.ehs_incidents "
        "DROP CONSTRAINT IF EXISTS ehs_incidents_site_diary_entry_id_fkey"
    )
    op.execute(
        "ALTER TABLE construction.progress_updates "
        "DROP CONSTRAINT IF EXISTS progress_updates_schedule_activity_id_fkey"
    )
    op.execute(
        "ALTER TABLE quality.snag_items DROP CONSTRAINT IF EXISTS snag_items_inspection_id_fkey"
    )
    _add_constraint_if_missing(
        "construction.site_diary_entries",
        "uq_site_diary_id_project",
        "UNIQUE (id, project_id)",
    )
    _add_constraint_if_missing(
        "construction.schedule_activities",
        "fk_schedule_predecessor_project",
        "FOREIGN KEY (predecessor_activity_id, project_id) "
        "REFERENCES construction.schedule_activities(id, project_id)",
    )
    _add_constraint_if_missing(
        "construction.ehs_incidents",
        "fk_ehs_diary_project",
        "FOREIGN KEY (site_diary_entry_id, project_id) "
        "REFERENCES construction.site_diary_entries(id, project_id)",
    )
    _add_constraint_if_missing(
        "construction.progress_updates",
        "fk_progress_activity_project",
        "FOREIGN KEY (schedule_activity_id, project_id) "
        "REFERENCES construction.schedule_activities(id, project_id)",
    )
    _add_constraint_if_missing(
        "quality.snag_items",
        "fk_snag_inspection_project",
        "FOREIGN KEY (inspection_id, project_id) REFERENCES quality.inspections(id, project_id)",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE quality.snag_items DROP CONSTRAINT IF EXISTS fk_snag_inspection_project"
    )
    op.execute(
        "ALTER TABLE construction.progress_updates "
        "DROP CONSTRAINT IF EXISTS fk_progress_activity_project"
    )
    op.execute(
        "ALTER TABLE construction.ehs_incidents DROP CONSTRAINT IF EXISTS fk_ehs_diary_project"
    )
    op.execute(
        "ALTER TABLE construction.schedule_activities "
        "DROP CONSTRAINT IF EXISTS fk_schedule_predecessor_project"
    )
    op.execute(
        "ALTER TABLE construction.site_diary_entries "
        "DROP CONSTRAINT IF EXISTS uq_site_diary_id_project"
    )
    _add_constraint_if_missing(
        "construction.schedule_activities",
        "schedule_activities_predecessor_activity_id_fkey",
        "FOREIGN KEY (predecessor_activity_id) REFERENCES construction.schedule_activities(id)",
    )
    _add_constraint_if_missing(
        "construction.ehs_incidents",
        "ehs_incidents_site_diary_entry_id_fkey",
        "FOREIGN KEY (site_diary_entry_id) REFERENCES construction.site_diary_entries(id)",
    )
    _add_constraint_if_missing(
        "construction.progress_updates",
        "progress_updates_schedule_activity_id_fkey",
        "FOREIGN KEY (schedule_activity_id) REFERENCES construction.schedule_activities(id)",
    )
    _add_constraint_if_missing(
        "quality.snag_items",
        "snag_items_inspection_id_fkey",
        "FOREIGN KEY (inspection_id) REFERENCES quality.inspections(id)",
    )
