"""Add Phase 8 customer-lifecycle integrity.

Revision ID: 0009_phase8_customer_lifecycle
Revises: 0008_phase7_change_quality
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision = "0009_phase8_customer_lifecycle"
down_revision = "0008_phase7_change_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE customers.customers
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE customers.bookings
      ADD COLUMN booking_document_id UUID REFERENCES documents.documents(id),
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ;
    ALTER TABLE customers.payment_plans
      ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id), ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ, ADD CONSTRAINT chk_payment_plan_amount CHECK (total_amount IS NULL OR total_amount >= 0),
      ADD CONSTRAINT chk_payment_plan_status CHECK (status IN ('active','completed','cancelled'));
    ALTER TABLE customers.payment_plan_installments
      ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id), ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ, ADD CONSTRAINT chk_installment_amount CHECK (amount IS NULL OR amount >= 0);
    ALTER TABLE customers.collections
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id), ADD COLUMN received_by UUID REFERENCES identity.users(id),
      ADD COLUMN allocated_at TIMESTAMPTZ, ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ,
      ADD CONSTRAINT chk_collection_amount CHECK (amount > 0);
    ALTER TABLE customers.possession_records
      ADD COLUMN evidence_document_id UUID REFERENCES documents.documents(id), ADD COLUMN handed_over_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), ADD COLUMN created_by UUID REFERENCES identity.users(id),
      ADD COLUMN updated_by UUID REFERENCES identity.users(id), ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
      ADD COLUMN archived_at TIMESTAMPTZ, ADD CONSTRAINT uq_possession_booking UNIQUE (booking_id);
    CREATE TABLE customers.registration_records (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), booking_id UUID NOT NULL UNIQUE REFERENCES customers.bookings(id),
      registration_date DATE, evidence_document_id UUID REFERENCES documents.documents(id), registered_by UUID REFERENCES identity.users(id),
      status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','scheduled','registered','cancelled')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      created_by UUID REFERENCES identity.users(id), updated_by UUID REFERENCES identity.users(id), version INTEGER NOT NULL DEFAULT 1,
      archived_at TIMESTAMPTZ);
    CREATE TABLE customers.booking_contracts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), booking_id UUID NOT NULL UNIQUE REFERENCES customers.bookings(id),
      contract_id UUID NOT NULL UNIQUE REFERENCES contracts.contracts(id), executed_document_id UUID NOT NULL REFERENCES documents.documents(id),
      linked_at TIMESTAMPTZ NOT NULL DEFAULT now(), linked_by UUID REFERENCES identity.users(id), version INTEGER NOT NULL DEFAULT 1,
      archived_at TIMESTAMPTZ);
    CREATE UNIQUE INDEX uq_active_booking_unit ON customers.bookings(unit_id) WHERE status <> 'cancelled' AND archived_at IS NULL;
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON customers.payment_plans FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON customers.payment_plan_installments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON customers.collections FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON customers.possession_records FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON customers.registration_records FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX customers.uq_active_booking_unit; DROP TABLE customers.booking_contracts; DROP TABLE customers.registration_records;
    DROP TRIGGER trg_set_updated_at ON customers.possession_records; DROP TRIGGER trg_set_updated_at ON customers.collections;
    DROP TRIGGER trg_set_updated_at ON customers.payment_plan_installments; DROP TRIGGER trg_set_updated_at ON customers.payment_plans;
    ALTER TABLE customers.possession_records DROP CONSTRAINT uq_possession_booking, DROP COLUMN evidence_document_id,
      DROP COLUMN handed_over_by, DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE customers.collections DROP CONSTRAINT chk_collection_amount, DROP COLUMN evidence_document_id, DROP COLUMN received_by,
      DROP COLUMN allocated_at, DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE customers.payment_plan_installments DROP CONSTRAINT chk_installment_amount, DROP COLUMN updated_at,
      DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE customers.payment_plans DROP CONSTRAINT chk_payment_plan_amount, DROP CONSTRAINT chk_payment_plan_status,
      DROP COLUMN updated_at, DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE customers.bookings DROP COLUMN booking_document_id, DROP COLUMN created_by, DROP COLUMN updated_by,
      DROP COLUMN version, DROP COLUMN archived_at;
    ALTER TABLE customers.customers DROP COLUMN created_by, DROP COLUMN updated_by, DROP COLUMN version, DROP COLUMN archived_at;
    """)
