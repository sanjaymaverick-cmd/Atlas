"""Add Phase 6 BIM, quantity, WBS, and material-traceability integrity.

Revision ID: 0007_phase6_project_controls
Revises: 0006_phase5_construction_quality
"""

from __future__ import annotations

from alembic import op

revision = "0007_phase6_project_controls"
down_revision = "0006_phase5_construction_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE design.bim_imports
          ADD COLUMN source_document_id UUID REFERENCES documents.documents(id),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;
        ALTER TABLE design.bim_objects
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT uq_bim_object_import_guid UNIQUE (bim_import_id, ifc_guid);
        ALTER TABLE quantities.cost_codes
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT chk_cost_code_wbs_level CHECK (wbs_level >= 1);
        ALTER TABLE quantities.quantity_items
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT chk_quantity_calculated_nonnegative
            CHECK (calculated_quantity IS NULL OR calculated_quantity >= 0),
          ADD CONSTRAINT chk_quantity_verified_nonnegative
            CHECK (verified_quantity IS NULL OR verified_quantity >= 0),
          ADD CONSTRAINT chk_quantity_final_nonnegative
            CHECK (final_approved_quantity IS NULL OR final_approved_quantity >= 0),
          ADD CONSTRAINT chk_quantity_tolerance CHECK (tolerance_pct BETWEEN 0 AND 100);
        ALTER TABLE inventory.materials
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT uq_material_name_unit UNIQUE (name, unit_of_measure);
        ALTER TABLE inventory.material_receipts
          DROP CONSTRAINT material_receipts_purchase_order_id_fkey,
          ALTER COLUMN quantity_received SET NOT NULL,
          ADD COLUMN batch_reference TEXT,
          ADD COLUMN certificate_document_id UUID REFERENCES documents.documents(id),
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT chk_material_receipt_quantity CHECK (quantity_received > 0);
        ALTER TABLE procurement.purchase_orders
          ADD CONSTRAINT uq_purchase_order_id_project UNIQUE (id, project_id);
        ALTER TABLE inventory.material_receipts
          ADD CONSTRAINT fk_material_receipt_po_project
          FOREIGN KEY (purchase_order_id, project_id)
          REFERENCES procurement.purchase_orders(id, project_id);
        ALTER TABLE inventory.material_issuances
          ALTER COLUMN quantity_issued SET NOT NULL,
          ADD COLUMN material_receipt_id UUID REFERENCES inventory.material_receipts(id),
          ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT chk_material_issuance_quantity CHECK (quantity_issued > 0);

        -- Existing Phase 0 rows cannot be safely assigned to a receipt without a
        -- business migration decision. The repository contains synthetic fixtures
        -- only; fail closed if any row prevents this integrity constraint.
        ALTER TABLE inventory.material_issuances
          ALTER COLUMN material_receipt_id SET NOT NULL;

        CREATE INDEX idx_bim_imports_project ON design.bim_imports(project_id);
        CREATE INDEX idx_quantity_items_project_status
          ON quantities.quantity_items(project_id, status);
        CREATE INDEX idx_material_receipts_project_date
          ON inventory.material_receipts(project_id, received_date);
        CREATE INDEX idx_material_issuances_receipt
          ON inventory.material_issuances(material_receipt_id);
        CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON quantities.cost_codes
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON inventory.materials
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON inventory.material_receipts
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON inventory.material_issuances
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER trg_set_updated_at ON inventory.material_issuances;
        DROP TRIGGER trg_set_updated_at ON inventory.material_receipts;
        DROP TRIGGER trg_set_updated_at ON inventory.materials;
        DROP TRIGGER trg_set_updated_at ON quantities.cost_codes;
        DROP INDEX inventory.idx_material_issuances_receipt;
        DROP INDEX inventory.idx_material_receipts_project_date;
        DROP INDEX quantities.idx_quantity_items_project_status;
        DROP INDEX design.idx_bim_imports_project;
        ALTER TABLE inventory.material_issuances
          DROP CONSTRAINT chk_material_issuance_quantity,
          DROP COLUMN material_receipt_id, DROP COLUMN evidence_document_id,
          DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at,
          ALTER COLUMN quantity_issued DROP NOT NULL;
        ALTER TABLE inventory.material_receipts
          DROP CONSTRAINT fk_material_receipt_po_project,
          DROP CONSTRAINT chk_material_receipt_quantity,
          DROP COLUMN batch_reference, DROP COLUMN certificate_document_id,
          DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at,
          ALTER COLUMN quantity_received DROP NOT NULL;
        ALTER TABLE inventory.material_receipts
          ADD CONSTRAINT material_receipts_purchase_order_id_fkey
          FOREIGN KEY (purchase_order_id) REFERENCES procurement.purchase_orders(id);
        ALTER TABLE procurement.purchase_orders
          DROP CONSTRAINT uq_purchase_order_id_project;
        ALTER TABLE inventory.materials
          DROP CONSTRAINT uq_material_name_unit,
          DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE quantities.quantity_items
          DROP CONSTRAINT chk_quantity_calculated_nonnegative,
          DROP CONSTRAINT chk_quantity_verified_nonnegative,
          DROP CONSTRAINT chk_quantity_final_nonnegative,
          DROP CONSTRAINT chk_quantity_tolerance,
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE quantities.cost_codes
          DROP CONSTRAINT chk_cost_code_wbs_level,
          DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        ALTER TABLE design.bim_objects
          DROP CONSTRAINT uq_bim_object_import_guid,
          DROP COLUMN created_by, DROP COLUMN archived_at;
        ALTER TABLE design.bim_imports
          DROP COLUMN source_document_id,
          DROP COLUMN created_by, DROP COLUMN updated_by,
          DROP COLUMN version, DROP COLUMN archived_at;
        """
    )
