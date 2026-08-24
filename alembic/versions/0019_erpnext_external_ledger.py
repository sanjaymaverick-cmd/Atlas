"""Migrate the Phase 9 persistence vocabulary to an external-ledger boundary.

Revision ID: 0019_erpnext_external_ledger
Revises: 0018_phase8_customer_integrity
"""

# ruff: noqa: E501 -- SQL migration statements retain their database vocabulary.

from __future__ import annotations

from alembic import op

revision = "0019_erpnext_external_ledger"
down_revision = "0018_phase8_customer_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('finance.tally_import_batches') IS NOT NULL
             AND to_regclass('finance.ledger_sync_batches') IS NULL THEN
            ALTER TABLE finance.tally_import_batches RENAME TO ledger_sync_batches;
          END IF;
          IF to_regclass('finance.tally_ledger_mappings') IS NOT NULL
             AND to_regclass('finance.ledger_account_mappings') IS NULL THEN
            ALTER TABLE finance.tally_ledger_mappings RENAME TO ledger_account_mappings;
          END IF;
          IF to_regclass('finance.tally_vouchers') IS NOT NULL
             AND to_regclass('finance.external_vouchers') IS NULL THEN
            ALTER TABLE finance.tally_vouchers RENAME TO external_vouchers;
          END IF;
        END $$;

        ALTER TABLE finance.ledger_sync_batches
          ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'erpnext';
        ALTER TABLE finance.ledger_account_mappings
          ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'erpnext';

        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='finance'
                     AND table_name='ledger_account_mappings' AND column_name='tally_ledger_name') THEN
            ALTER TABLE finance.ledger_account_mappings RENAME COLUMN tally_ledger_name TO external_account_name;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='finance'
                     AND table_name='ledger_account_mappings' AND column_name='erp_reference_type') THEN
            ALTER TABLE finance.ledger_account_mappings RENAME COLUMN erp_reference_type TO atlas_reference_type;
            ALTER TABLE finance.ledger_account_mappings RENAME COLUMN erp_reference_id TO atlas_reference_id;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='finance'
                     AND table_name='external_vouchers' AND column_name='import_batch_id') THEN
            ALTER TABLE finance.external_vouchers RENAME COLUMN import_batch_id TO sync_batch_id;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='finance'
                     AND table_name='reconciliations' AND column_name='erp_reference_type') THEN
            ALTER TABLE finance.reconciliations RENAME COLUMN erp_reference_type TO atlas_reference_type;
            ALTER TABLE finance.reconciliations RENAME COLUMN erp_reference_id TO atlas_reference_id;
            ALTER TABLE finance.reconciliations RENAME COLUMN tally_voucher_id TO external_voucher_id;
            ALTER TABLE finance.reconciliations RENAME COLUMN erp_amount TO atlas_amount;
            ALTER TABLE finance.reconciliations RENAME COLUMN tally_amount TO external_amount;
          END IF;
        END $$;

        DO $$ DECLARE constraint_name TEXT;
        BEGIN
          SELECT c.conname INTO constraint_name
          FROM pg_constraint c
          JOIN pg_class t ON t.oid=c.conrelid
          JOIN pg_namespace n ON n.oid=t.relnamespace
          WHERE n.nspname='finance' AND t.relname='reconciliations'
            AND c.contype='c' AND pg_get_constraintdef(c.oid) LIKE '%discrepancy_type%'
          LIMIT 1;
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE finance.reconciliations DROP CONSTRAINT %I', constraint_name);
          END IF;
        END $$;

        UPDATE finance.reconciliations SET discrepancy_type='missing_in_external_ledger'
          WHERE discrepancy_type='missing_in_tally';
        UPDATE finance.reconciliations SET discrepancy_type='missing_in_atlas'
          WHERE discrepancy_type='missing_in_erp';

        ALTER TABLE finance.ledger_sync_batches DROP CONSTRAINT IF EXISTS ledger_sync_batches_provider_check;
        ALTER TABLE finance.ledger_sync_batches ADD CONSTRAINT ledger_sync_batches_provider_check
          CHECK (provider ~ '^[a-z][a-z0-9_]{1,31}$');
        ALTER TABLE finance.ledger_account_mappings DROP CONSTRAINT IF EXISTS ledger_account_mappings_provider_check;
        ALTER TABLE finance.ledger_account_mappings ADD CONSTRAINT ledger_account_mappings_provider_check
          CHECK (provider ~ '^[a-z][a-z0-9_]{1,31}$');
        ALTER TABLE finance.reconciliations ADD CONSTRAINT reconciliations_discrepancy_type_check
          CHECK (discrepancy_type IN ('missing_in_external_ledger','missing_in_atlas','amount_mismatch',
          'wrong_entity','wrong_project','duplicate_voucher','unallocated_receipt',
          'schedule_not_updated','obligation_still_open'));

        DROP INDEX IF EXISTS finance.idx_tally_batches_entity_status;
        DROP INDEX IF EXISTS finance.idx_tally_vouchers_batch;
        CREATE INDEX IF NOT EXISTS idx_ledger_sync_batches_entity_status
          ON finance.ledger_sync_batches(legal_entity_id, status);
        CREATE INDEX IF NOT EXISTS idx_external_vouchers_batch
          ON finance.external_vouchers(sync_batch_id);

        UPDATE identity.permissions SET code='finance.ledger.sync'
          WHERE code='finance.tally.import';
        UPDATE identity.permissions SET code='finance.ledger.validate'
          WHERE code='finance.tally.validate';
        """
    )


def downgrade() -> None:
    # This terminology migration is intentionally irreversible. Reintroducing
    # provider-specific persistence would invalidate post-upgrade API contracts.
    pass
