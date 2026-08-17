"""Strengthen Phase 3 land, finance, and compliance records.

Revision ID: 0004_phase3_land_compliance
Revises: 0003_document_versioning
"""

from __future__ import annotations

from alembic import op

revision = "0004_phase3_land_compliance"
down_revision = "0003_document_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE land.land_legal_approvals
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;
        ALTER TABLE land.loan_obligations
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;
        ALTER TABLE compliance.rera_registrations
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ,
          ADD CONSTRAINT uq_rera_registration_number UNIQUE (registration_number);
        ALTER TABLE compliance.compliance_obligations
          ADD COLUMN created_by UUID REFERENCES identity.users(id),
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN archived_at TIMESTAMPTZ;

        CREATE TABLE land.due_diligence_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          land_parcel_id UUID NOT NULL REFERENCES land.land_parcels(id),
          category TEXT NOT NULL,
          title TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT 'pending'
            CHECK (result IN ('pending','clear','issue','waived')),
          evidence_document_id UUID REFERENCES documents.documents(id),
          notes TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID REFERENCES identity.users(id),
          updated_by UUID REFERENCES identity.users(id),
          version INTEGER NOT NULL DEFAULT 1,
          archived_at TIMESTAMPTZ
        );
        CREATE TABLE land.loan_installments (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          loan_obligation_id UUID NOT NULL REFERENCES land.loan_obligations(id),
          due_date DATE NOT NULL,
          amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
          instrument_type TEXT NOT NULL DEFAULT 'emi'
            CHECK (instrument_type IN ('emi','pdc','other')),
          reference_number TEXT,
          status TEXT NOT NULL DEFAULT 'scheduled'
            CHECK (status IN ('scheduled','paid','bounced','waived','overdue')),
          paid_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by UUID REFERENCES identity.users(id),
          updated_by UUID REFERENCES identity.users(id),
          version INTEGER NOT NULL DEFAULT 1,
          archived_at TIMESTAMPTZ,
          UNIQUE (loan_obligation_id, due_date, instrument_type)
        );
        CREATE INDEX idx_due_diligence_parcel
          ON land.due_diligence_items(land_parcel_id);
        CREATE INDEX idx_loan_installments_due
          ON land.loan_installments(due_date, status);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE land.loan_installments;
        DROP TABLE land.due_diligence_items;
        ALTER TABLE compliance.compliance_obligations
          DROP COLUMN archived_at, DROP COLUMN version,
          DROP COLUMN updated_by, DROP COLUMN created_by;
        ALTER TABLE compliance.rera_registrations
          DROP CONSTRAINT uq_rera_registration_number,
          DROP COLUMN archived_at, DROP COLUMN version,
          DROP COLUMN updated_by, DROP COLUMN created_by;
        ALTER TABLE land.loan_obligations
          DROP COLUMN archived_at, DROP COLUMN version,
          DROP COLUMN updated_by, DROP COLUMN created_by;
        ALTER TABLE land.land_legal_approvals
          DROP COLUMN archived_at, DROP COLUMN version,
          DROP COLUMN updated_by, DROP COLUMN created_by;
        """
    )
