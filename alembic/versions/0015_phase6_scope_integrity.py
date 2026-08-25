"""Enforce Phase 6 project-scoped references.

Revision ID: 0015_phase6_scope_integrity
Revises: 0014_phase5_meeting_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0015_phase6_scope_integrity"
down_revision = "0014_phase5_meeting_integrity"
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
        "UPDATE design.bim_objects o SET project_id = i.project_id "
        "FROM design.bim_imports i "
        "WHERE o.bim_import_id = i.id AND o.project_id IS NULL"
    )
    op.execute("ALTER TABLE design.bim_objects ALTER COLUMN project_id SET NOT NULL")

    _add_constraint_if_missing(
        "documents.documents", "uq_documents_id_project", "UNIQUE (id, project_id)"
    )
    _add_constraint_if_missing(
        "design.bim_imports", "uq_bim_import_id_project", "UNIQUE (id, project_id)"
    )
    _add_constraint_if_missing(
        "design.bim_objects", "uq_bim_object_id_project", "UNIQUE (id, project_id)"
    )
    _add_constraint_if_missing(
        "quantities.cost_codes", "uq_cost_code_id_project", "UNIQUE (id, project_id)"
    )
    _add_constraint_if_missing(
        "inventory.material_receipts",
        "uq_material_receipt_scope",
        "UNIQUE (id, project_id, material_id)",
    )

    for table, constraint in (
        ("design.bim_imports", "bim_imports_source_document_id_fkey"),
        ("design.bim_objects", "bim_objects_bim_import_id_fkey"),
        ("quantities.quantity_items", "quantity_items_cost_code_id_fkey"),
        ("quantities.quantity_items", "quantity_items_bim_object_id_fkey"),
        ("inventory.material_receipts", "material_receipts_certificate_document_id_fkey"),
        ("inventory.material_issuances", "material_issuances_material_receipt_id_fkey"),
        ("inventory.material_issuances", "material_issuances_evidence_document_id_fkey"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")

    _add_constraint_if_missing(
        "design.bim_imports",
        "fk_bim_import_source_project",
        "FOREIGN KEY (source_document_id, project_id) "
        "REFERENCES documents.documents(id, project_id)",
    )
    _add_constraint_if_missing(
        "design.bim_objects",
        "fk_bim_object_import_project",
        "FOREIGN KEY (bim_import_id, project_id) REFERENCES design.bim_imports(id, project_id)",
    )
    _add_constraint_if_missing(
        "quantities.quantity_items",
        "fk_quantity_cost_code_project",
        "FOREIGN KEY (cost_code_id, project_id) REFERENCES quantities.cost_codes(id, project_id)",
    )
    _add_constraint_if_missing(
        "quantities.quantity_items",
        "fk_quantity_bim_object_project",
        "FOREIGN KEY (bim_object_id, project_id) REFERENCES design.bim_objects(id, project_id)",
    )
    _add_constraint_if_missing(
        "inventory.material_receipts",
        "fk_material_receipt_certificate_project",
        "FOREIGN KEY (certificate_document_id, project_id) "
        "REFERENCES documents.documents(id, project_id)",
    )
    _add_constraint_if_missing(
        "inventory.material_issuances",
        "fk_material_issuance_receipt_scope",
        "FOREIGN KEY (material_receipt_id, project_id, material_id) "
        "REFERENCES inventory.material_receipts(id, project_id, material_id)",
    )
    _add_constraint_if_missing(
        "inventory.material_issuances",
        "fk_material_issuance_evidence_project",
        "FOREIGN KEY (evidence_document_id, project_id) "
        "REFERENCES documents.documents(id, project_id)",
    )


def downgrade() -> None:
    for table, constraint in (
        ("inventory.material_issuances", "fk_material_issuance_evidence_project"),
        ("inventory.material_issuances", "fk_material_issuance_receipt_scope"),
        ("inventory.material_receipts", "fk_material_receipt_certificate_project"),
        ("quantities.quantity_items", "fk_quantity_bim_object_project"),
        ("quantities.quantity_items", "fk_quantity_cost_code_project"),
        ("design.bim_objects", "fk_bim_object_import_project"),
        ("design.bim_imports", "fk_bim_import_source_project"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")

    _add_constraint_if_missing(
        "design.bim_imports",
        "bim_imports_source_document_id_fkey",
        "FOREIGN KEY (source_document_id) REFERENCES documents.documents(id)",
    )
    _add_constraint_if_missing(
        "design.bim_objects",
        "bim_objects_bim_import_id_fkey",
        "FOREIGN KEY (bim_import_id) REFERENCES design.bim_imports(id)",
    )
    _add_constraint_if_missing(
        "quantities.quantity_items",
        "quantity_items_cost_code_id_fkey",
        "FOREIGN KEY (cost_code_id) REFERENCES quantities.cost_codes(id)",
    )
    _add_constraint_if_missing(
        "quantities.quantity_items",
        "quantity_items_bim_object_id_fkey",
        "FOREIGN KEY (bim_object_id) REFERENCES design.bim_objects(id)",
    )
    _add_constraint_if_missing(
        "inventory.material_receipts",
        "material_receipts_certificate_document_id_fkey",
        "FOREIGN KEY (certificate_document_id) REFERENCES documents.documents(id)",
    )
    _add_constraint_if_missing(
        "inventory.material_issuances",
        "material_issuances_material_receipt_id_fkey",
        "FOREIGN KEY (material_receipt_id) REFERENCES inventory.material_receipts(id)",
    )
    _add_constraint_if_missing(
        "inventory.material_issuances",
        "material_issuances_evidence_document_id_fkey",
        "FOREIGN KEY (evidence_document_id) REFERENCES documents.documents(id)",
    )

    op.execute("ALTER TABLE design.bim_objects ALTER COLUMN project_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE inventory.material_receipts "
        "DROP CONSTRAINT IF EXISTS uq_material_receipt_scope"
    )
    op.execute(
        "ALTER TABLE quantities.cost_codes DROP CONSTRAINT IF EXISTS uq_cost_code_id_project"
    )
    op.execute("ALTER TABLE design.bim_objects DROP CONSTRAINT IF EXISTS uq_bim_object_id_project")
    op.execute("ALTER TABLE design.bim_imports DROP CONSTRAINT IF EXISTS uq_bim_import_id_project")
    op.execute("ALTER TABLE documents.documents DROP CONSTRAINT IF EXISTS uq_documents_id_project")
