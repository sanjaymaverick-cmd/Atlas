"""Add Phase 2 document versioning invariants.

Revision ID: 0003_document_versioning
Revises: 0002_webauthn_challenges
"""

from __future__ import annotations

from alembic import op

revision = "0003_document_versioning"
down_revision = "0002_webauthn_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents.documents
          ADD COLUMN updated_by UUID REFERENCES identity.users(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE documents.documents
          ALTER COLUMN project_id SET NOT NULL;
        ALTER TABLE documents.document_versions
          ALTER COLUMN checksum_sha256 SET NOT NULL;
        ALTER TABLE documents.document_versions
          ADD CONSTRAINT ck_document_versions_checksum_sha256
          CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
          ADD CONSTRAINT ck_document_versions_status
          CHECK (status IN (
            'draft','virus_scanned','quarantined','under_review','approved','issued','superseded'
          )),
          ADD CONSTRAINT uq_document_versions_storage_key
          UNIQUE (object_storage_key);
        ALTER TABLE documents.document_versions
          ADD CONSTRAINT uq_document_versions_document_revision
          UNIQUE (document_id, revision_code);
        CREATE TABLE documents.preview_grants (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          document_version_id UUID NOT NULL REFERENCES documents.document_versions(id),
          session_id UUID NOT NULL REFERENCES identity.sessions(id),
          created_by UUID NOT NULL REFERENCES identity.users(id),
          token_hash TEXT NOT NULL UNIQUE,
          watermark_text TEXT NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          revoked_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE documents.export_requests (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          document_version_id UUID NOT NULL REFERENCES documents.document_versions(id),
          requested_by UUID NOT NULL REFERENCES identity.users(id),
          approved_by UUID REFERENCES identity.users(id),
          reason TEXT NOT NULL,
          decision_reason TEXT,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','approved','rejected','expired','downloaded')),
          expires_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          version INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX idx_preview_grants_expiry
          ON documents.preview_grants(expires_at) WHERE revoked_at IS NULL;
        CREATE INDEX idx_export_requests_revision
          ON documents.export_requests(document_version_id, status);
        CREATE UNIQUE INDEX uq_export_requests_pending_requester
          ON documents.export_requests(document_version_id, requested_by)
          WHERE status = 'pending';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE documents.export_requests;
        DROP TABLE documents.preview_grants;
        ALTER TABLE documents.document_versions
          DROP CONSTRAINT uq_document_versions_document_revision,
          DROP CONSTRAINT uq_document_versions_storage_key,
          DROP CONSTRAINT ck_document_versions_status,
          DROP CONSTRAINT ck_document_versions_checksum_sha256;
        ALTER TABLE documents.document_versions
          ALTER COLUMN checksum_sha256 DROP NOT NULL;
        ALTER TABLE documents.documents
          ALTER COLUMN project_id DROP NOT NULL;
        ALTER TABLE documents.documents
          DROP COLUMN version,
          DROP COLUMN updated_by;
        """
    )
