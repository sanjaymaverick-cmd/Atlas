"""Add Phase 4 commercial integrity columns and constraints.

Revision ID: 0005_phase4_commercial_integrity
Revises: 0004_phase3_land_compliance
"""

from __future__ import annotations

from alembic import op

revision = "0005_phase4_commercial_integrity"
down_revision = "0004_phase3_land_compliance"
branch_labels = None
depends_on = None


AUDITED_TABLES = (
    "budget.budgets",
    "budget.budget_lines",
    "procurement.purchase_orders",
    "contracts.contracts",
    "contracts.contract_milestones",
    "vendor_onboarding.vendor_onboardings",
    "vendor_onboarding.insurance_policies",
    "vendor_onboarding.labour_compliance_records",
)


def upgrade() -> None:
    for table in AUDITED_TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
              ADD COLUMN created_by UUID REFERENCES identity.users(id),
              ADD COLUMN updated_by UUID REFERENCES identity.users(id),
              ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
              ADD COLUMN archived_at TIMESTAMPTZ
            """
        )
    op.execute(
        """
        ALTER TABLE procurement.purchase_order_lines
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;
        ALTER TABLE vendor_onboarding.kyc_records
          ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id),
          ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;

        ALTER TABLE budget.budgets
          ADD CONSTRAINT chk_budget_total_nonneg CHECK (total_amount >= 0);
        ALTER TABLE budget.budget_lines
          ADD CONSTRAINT chk_budget_line_amounts_nonneg
          CHECK (planned_amount >= 0 AND committed_amount >= 0 AND actual_amount >= 0);
        ALTER TABLE procurement.purchase_order_lines
          ADD CONSTRAINT chk_po_line_quantity_nonneg CHECK (quantity IS NULL OR quantity >= 0),
          ADD CONSTRAINT chk_po_line_unit_price_nonneg
            CHECK (unit_price IS NULL OR unit_price >= 0),
          ADD CONSTRAINT chk_po_line_amount_nonneg CHECK (amount IS NULL OR amount >= 0);
        ALTER TABLE contracts.contracts
          ADD CONSTRAINT chk_contract_value_nonneg CHECK (value IS NULL OR value >= 0);
        ALTER TABLE contracts.contract_milestones
          ADD CONSTRAINT chk_contract_milestone_amount_nonneg CHECK (amount IS NULL OR amount >= 0);
        ALTER TABLE vendor_onboarding.vendor_onboardings
          ADD CONSTRAINT uq_vendor_onboarding_vendor UNIQUE (vendor_id);
        ALTER TABLE vendor_onboarding.insurance_policies
          ADD CONSTRAINT chk_insurance_sum_nonneg CHECK (sum_insured IS NULL OR sum_insured >= 0);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE vendor_onboarding.insurance_policies DROP CONSTRAINT chk_insurance_sum_nonneg;
        ALTER TABLE vendor_onboarding.vendor_onboardings
          DROP CONSTRAINT uq_vendor_onboarding_vendor;
        ALTER TABLE contracts.contract_milestones
          DROP CONSTRAINT chk_contract_milestone_amount_nonneg;
        ALTER TABLE contracts.contracts DROP CONSTRAINT chk_contract_value_nonneg;
        ALTER TABLE procurement.purchase_order_lines
          DROP CONSTRAINT chk_po_line_quantity_nonneg,
          DROP CONSTRAINT chk_po_line_unit_price_nonneg,
          DROP CONSTRAINT chk_po_line_amount_nonneg;
        ALTER TABLE budget.budget_lines DROP CONSTRAINT chk_budget_line_amounts_nonneg;
        ALTER TABLE budget.budgets DROP CONSTRAINT chk_budget_total_nonneg;

        ALTER TABLE vendor_onboarding.kyc_records
          DROP COLUMN evidence_document_id,
          DROP COLUMN updated_at,
          DROP COLUMN created_by,
          DROP COLUMN updated_by,
          DROP COLUMN version,
          DROP COLUMN archived_at;
        ALTER TABLE procurement.purchase_order_lines
          DROP COLUMN updated_at,
          DROP COLUMN created_by,
          DROP COLUMN updated_by,
          DROP COLUMN version,
          DROP COLUMN archived_at;
        """
    )
    for table in reversed(AUDITED_TABLES):
        op.execute(
            f"""
            ALTER TABLE {table}
              DROP COLUMN created_by,
              DROP COLUMN updated_by,
              DROP COLUMN version,
              DROP COLUMN archived_at
            """
        )
