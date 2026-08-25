"""Add scoped, audited Phase 5 meeting workflows.

Revision ID: 0014_phase5_meeting_integrity
Revises: 0013_phase5_scope_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0014_phase5_meeting_integrity"
down_revision = "0013_phase5_scope_integrity"
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
        "ALTER TABLE construction.meeting_registers "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES identity.users(id), "
        "ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES identity.users(id), "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1, "
        "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"
    )
    op.execute(
        "UPDATE construction.meeting_registers SET status = 'recorded' "
        "WHERE status NOT IN ('recorded', 'closed')"
    )
    op.execute(
        "ALTER TABLE construction.meeting_registers "
        "DROP CONSTRAINT IF EXISTS ck_meeting_registers_status, "
        "ADD CONSTRAINT ck_meeting_registers_status "
        "CHECK (status IN ('recorded','closed'))"
    )
    _add_constraint_if_missing(
        "construction.meeting_registers",
        "uq_meeting_register_id_project",
        "UNIQUE (id, project_id)",
    )
    op.execute(
        "ALTER TABLE construction.meeting_action_items "
        "ADD COLUMN IF NOT EXISTS project_id UUID, "
        "ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES identity.users(id), "
        "ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES identity.users(id), "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1, "
        "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ"
    )
    op.execute(
        "UPDATE construction.meeting_action_items a SET project_id = m.project_id "
        "FROM construction.meeting_registers m WHERE a.meeting_register_id = m.id "
        "AND a.project_id IS NULL"
    )
    op.execute("ALTER TABLE construction.meeting_action_items ALTER COLUMN project_id SET NOT NULL")
    _add_constraint_if_missing(
        "construction.meeting_action_items",
        "meeting_action_items_project_id_fkey",
        "FOREIGN KEY (project_id) REFERENCES organization.projects(id)",
    )
    op.execute(
        "ALTER TABLE construction.meeting_action_items "
        "DROP CONSTRAINT IF EXISTS meeting_action_items_meeting_register_id_fkey"
    )
    _add_constraint_if_missing(
        "construction.meeting_action_items",
        "fk_meeting_action_project",
        "FOREIGN KEY (meeting_register_id, project_id) "
        "REFERENCES construction.meeting_registers(id, project_id)",
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meeting_registers_project_date "
        "ON construction.meeting_registers(project_id, meeting_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meeting_action_items_meeting_status "
        "ON construction.meeting_action_items(meeting_register_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS construction.idx_meeting_action_items_meeting_status")
    op.execute("DROP INDEX IF EXISTS construction.idx_meeting_registers_project_date")
    op.execute(
        "ALTER TABLE construction.meeting_action_items "
        "DROP CONSTRAINT IF EXISTS fk_meeting_action_project, "
        "ADD CONSTRAINT meeting_action_items_meeting_register_id_fkey "
        "FOREIGN KEY (meeting_register_id) REFERENCES construction.meeting_registers(id), "
        "DROP CONSTRAINT IF EXISTS meeting_action_items_project_id_fkey, "
        "DROP COLUMN IF EXISTS project_id, "
        "DROP COLUMN IF EXISTS created_by, "
        "DROP COLUMN IF EXISTS updated_by, "
        "DROP COLUMN IF EXISTS version, "
        "DROP COLUMN IF EXISTS archived_at"
    )
    op.execute(
        "ALTER TABLE construction.meeting_registers "
        "DROP CONSTRAINT IF EXISTS uq_meeting_register_id_project, "
        "DROP CONSTRAINT IF EXISTS ck_meeting_registers_status, "
        "DROP COLUMN IF EXISTS updated_at, "
        "DROP COLUMN IF EXISTS created_by, "
        "DROP COLUMN IF EXISTS updated_by, "
        "DROP COLUMN IF EXISTS version, "
        "DROP COLUMN IF EXISTS archived_at"
    )
