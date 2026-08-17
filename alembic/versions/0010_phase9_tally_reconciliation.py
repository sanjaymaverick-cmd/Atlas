"""Add Phase 9 Tally reconciliation integrity.

Revision ID: 0010_phase9_tally_reconciliation
Revises: 0009_phase8_customer_lifecycle
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision = "0010_phase9_tally_reconciliation"
down_revision = "0009_phase8_customer_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE finance.tally_import_batches (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), legal_entity_id UUID NOT NULL REFERENCES organization.legal_entities(id),
      source_document_id UUID NOT NULL REFERENCES documents.documents(id), content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
      period_start DATE, period_end DATE, status TEXT NOT NULL DEFAULT 'pending_validation' CHECK (status IN ('pending_validation','validated','rejected','imported')),
      validation_summary JSONB NOT NULL DEFAULT '{}'::jsonb, imported_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_by UUID REFERENCES identity.users(id), updated_by UUID REFERENCES identity.users(id),
      version INTEGER NOT NULL DEFAULT 1, archived_at TIMESTAMPTZ,
      CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start), UNIQUE (legal_entity_id, content_sha256));
    CREATE TABLE finance.tally_ledger_mappings (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), legal_entity_id UUID NOT NULL REFERENCES organization.legal_entities(id), tally_ledger_name TEXT NOT NULL,
      erp_reference_type TEXT NOT NULL, erp_reference_id UUID NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_by UUID REFERENCES identity.users(id),
      updated_by UUID REFERENCES identity.users(id), version INTEGER NOT NULL DEFAULT 1, archived_at TIMESTAMPTZ,
      UNIQUE (legal_entity_id, tally_ledger_name));
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM finance.tally_vouchers) THEN
        RAISE EXCEPTION 'Phase 9 requires an explicit controlled migration plan for pre-existing Tally vouchers';
      END IF;
    END $$;
    ALTER TABLE finance.tally_vouchers
      ADD COLUMN import_batch_id UUID REFERENCES finance.tally_import_batches(id), ADD COLUMN project_id UUID REFERENCES organization.projects(id),
      ADD COLUMN external_id TEXT, ADD COLUMN currency_code TEXT NOT NULL DEFAULT 'INR', ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id), ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE finance.tally_vouchers ALTER COLUMN import_batch_id SET NOT NULL, ALTER COLUMN external_id SET NOT NULL, ALTER COLUMN voucher_type SET NOT NULL,
      ALTER COLUMN voucher_number SET NOT NULL, ALTER COLUMN voucher_date SET NOT NULL, ALTER COLUMN amount SET NOT NULL,
      ALTER COLUMN ledger_reference SET NOT NULL, ADD CONSTRAINT chk_tally_voucher_amount CHECK (amount >= 0),
      ADD CONSTRAINT chk_tally_currency CHECK (currency_code ~ '^[A-Z]{3}$'), ADD CONSTRAINT uq_tally_external_id UNIQUE (legal_entity_id, external_id);
    ALTER TABLE finance.reconciliations
      ALTER COLUMN discrepancy_type SET NOT NULL, ADD COLUMN erp_amount NUMERIC(16,2), ADD COLUMN tally_amount NUMERIC(16,2),
      ADD COLUMN reviewed_at TIMESTAMPTZ, ADD COLUMN resolution_code TEXT, ADD COLUMN resolution_note TEXT,
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ,
      DROP CONSTRAINT reconciliations_status_check,
      ADD CONSTRAINT chk_reconciliation_status CHECK (status IN ('open','under_review','reconciled','accepted_exception')),
      ADD CONSTRAINT chk_reconciliation_type CHECK (discrepancy_type IN ('missing_in_tally','missing_in_erp','amount_mismatch','wrong_entity','wrong_project','duplicate_voucher','unallocated_receipt','schedule_not_updated','obligation_still_open')),
      ADD CONSTRAINT chk_reconciliation_erp_amount CHECK (erp_amount IS NULL OR erp_amount >= 0),
      ADD CONSTRAINT chk_reconciliation_tally_amount CHECK (tally_amount IS NULL OR tally_amount >= 0);
    CREATE INDEX idx_tally_batches_entity_status ON finance.tally_import_batches(legal_entity_id, status);
    CREATE INDEX idx_tally_vouchers_batch ON finance.tally_vouchers(import_batch_id);
    CREATE INDEX idx_reconciliations_entity_status ON finance.reconciliations(legal_entity_id, status);
    CREATE UNIQUE INDEX uq_reconciliation_fact ON finance.reconciliations(
      erp_reference_type, erp_reference_id, COALESCE(tally_voucher_id, '00000000-0000-0000-0000-000000000000'::uuid), discrepancy_type);
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON finance.tally_import_batches FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON finance.tally_ledger_mappings FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX finance.uq_reconciliation_fact; DROP INDEX finance.idx_reconciliations_entity_status; DROP INDEX finance.idx_tally_vouchers_batch; DROP INDEX finance.idx_tally_batches_entity_status;
    ALTER TABLE finance.reconciliations DROP CONSTRAINT chk_reconciliation_tally_amount,
      DROP CONSTRAINT chk_reconciliation_erp_amount, DROP CONSTRAINT chk_reconciliation_type, DROP CONSTRAINT chk_reconciliation_status,
      ADD CONSTRAINT reconciliations_status_check CHECK (status IN ('open','under_review','reconciled')),
      DROP COLUMN archived_at, DROP COLUMN version, DROP COLUMN updated_by, DROP COLUMN created_by, DROP COLUMN resolution_note,
      DROP COLUMN resolution_code, DROP COLUMN reviewed_at, DROP COLUMN tally_amount, DROP COLUMN erp_amount;
    ALTER TABLE finance.tally_vouchers DROP CONSTRAINT uq_tally_external_id, DROP CONSTRAINT chk_tally_currency,
      DROP CONSTRAINT chk_tally_voucher_amount, DROP COLUMN archived_at, DROP COLUMN version, DROP COLUMN updated_by,
      DROP COLUMN created_by, DROP COLUMN currency_code, DROP COLUMN external_id, DROP COLUMN project_id, DROP COLUMN import_batch_id;
    DROP TABLE finance.tally_ledger_mappings; DROP TABLE finance.tally_import_batches;
    """)
