"""Add structured Phase 6 BIM object mappings.

Revision ID: 0016_phase6_bim_mapping
Revises: 0015_phase6_scope_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0016_phase6_bim_mapping"
down_revision = "0015_phase6_scope_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE design.bim_objects "
        "ADD COLUMN IF NOT EXISTS work_package TEXT, "
        "ADD COLUMN IF NOT EXISTS material_id UUID"
    )
    op.execute(
        """DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'bim_objects_material_id_fkey'
              AND conrelid = 'design.bim_objects'::regclass
          ) THEN
            ALTER TABLE design.bim_objects
              ADD CONSTRAINT bim_objects_material_id_fkey
              FOREIGN KEY (material_id) REFERENCES inventory.materials(id);
          END IF;
        END
        $$"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bim_objects_import ON design.bim_objects(bim_import_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS design.idx_bim_objects_import")
    op.execute(
        "ALTER TABLE design.bim_objects "
        "DROP CONSTRAINT IF EXISTS bim_objects_material_id_fkey, "
        "DROP COLUMN IF EXISTS material_id, "
        "DROP COLUMN IF EXISTS work_package"
    )
