"""Add provider-neutral Phase 11 AI safety boundaries.

Revision ID: 0012_phase11_ai_safety
Revises: 0011_phase10_reporting
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision = "0012_phase11_ai_safety"
down_revision = "0011_phase10_reporting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM ai.ai_queries) OR EXISTS (SELECT 1 FROM ai.ai_recommendations) OR EXISTS (SELECT 1 FROM ai.ai_authority_log) THEN
        RAISE EXCEPTION 'Phase 11 requires an explicit privacy migration plan for pre-existing AI content';
      END IF;
    END $$;
    ALTER TABLE ai.ai_authority_log RENAME COLUMN action_attempted TO action_code;
    ALTER TABLE ai.ai_authority_log RENAME COLUMN reason TO reason_code;
    ALTER TABLE ai.ai_queries DROP CONSTRAINT ai_queries_status_check, DROP COLUMN query_text, DROP COLUMN response_text,
      ALTER COLUMN user_id SET NOT NULL, ADD COLUMN legal_entity_id UUID REFERENCES organization.legal_entities(id),
      ADD COLUMN project_id UUID REFERENCES organization.projects(id), ADD COLUMN request_digest TEXT NOT NULL,
      ADD COLUMN request_length INTEGER NOT NULL, ADD COLUMN authority_level INTEGER NOT NULL,
      ADD COLUMN response_digest TEXT, ADD COLUMN response_length INTEGER, ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ,
      ALTER COLUMN intent_classification SET NOT NULL, ALTER COLUMN status SET DEFAULT 'pending',
      ADD CONSTRAINT chk_ai_request_digest CHECK (request_digest ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT chk_ai_request_length CHECK (request_length BETWEEN 1 AND 12000),
      ADD CONSTRAINT chk_ai_authority_level CHECK (authority_level BETWEEN 1 AND 4),
      ADD CONSTRAINT chk_ai_response_digest CHECK (response_digest IS NULL OR response_digest ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT chk_ai_response_length CHECK (response_length IS NULL OR response_length >= 0),
      ADD CONSTRAINT chk_ai_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
      ADD CONSTRAINT chk_ai_query_status CHECK (status IN ('pending','answered','declined_low_confidence','blocked_authority','blocked_prompt_injection','hosting_not_configured','failed'));
    ALTER TABLE ai.ai_recommendations DROP COLUMN recommendation_text, ADD COLUMN content_document_id UUID NOT NULL REFERENCES documents.documents(id),
      ADD COLUMN recommendation_digest TEXT NOT NULL, ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      ADD COLUMN created_by UUID REFERENCES identity.users(id), ADD COLUMN updated_by UUID REFERENCES identity.users(id),
      ADD COLUMN version INTEGER NOT NULL DEFAULT 1, ADD COLUMN archived_at TIMESTAMPTZ,
      ADD CONSTRAINT chk_ai_recommendation_digest CHECK (recommendation_digest ~ '^[0-9a-f]{64}$');
    CREATE INDEX idx_ai_queries_scope_created ON ai.ai_queries(legal_entity_id, project_id, created_at);
    CREATE INDEX idx_ai_authority_query ON ai.ai_authority_log(ai_query_id);
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON ai.ai_queries FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON ai.ai_recommendations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX ai.idx_ai_authority_query; DROP INDEX ai.idx_ai_queries_scope_created;
    ALTER TABLE ai.ai_recommendations DROP CONSTRAINT chk_ai_recommendation_digest, DROP COLUMN archived_at, DROP COLUMN version,
      DROP COLUMN updated_by, DROP COLUMN created_by, DROP COLUMN updated_at, DROP COLUMN recommendation_digest,
      DROP COLUMN content_document_id, ADD COLUMN recommendation_text TEXT NOT NULL;
    ALTER TABLE ai.ai_queries DROP CONSTRAINT chk_ai_query_status, DROP CONSTRAINT chk_ai_confidence,
      DROP CONSTRAINT chk_ai_response_length, DROP CONSTRAINT chk_ai_response_digest, DROP CONSTRAINT chk_ai_authority_level,
      DROP CONSTRAINT chk_ai_request_length, DROP CONSTRAINT chk_ai_request_digest, DROP COLUMN archived_at, DROP COLUMN version,
      DROP COLUMN updated_by, DROP COLUMN created_by, DROP COLUMN updated_at, DROP COLUMN response_length, DROP COLUMN response_digest,
      DROP COLUMN authority_level, DROP COLUMN request_length, DROP COLUMN request_digest, DROP COLUMN project_id, DROP COLUMN legal_entity_id,
      ADD COLUMN response_text TEXT, ADD COLUMN query_text TEXT NOT NULL, ALTER COLUMN user_id DROP NOT NULL,
      ADD CONSTRAINT ai_queries_status_check CHECK (status IN ('answered','declined_low_confidence','blocked_authority'));
    ALTER TABLE ai.ai_authority_log RENAME COLUMN action_code TO action_attempted;
    ALTER TABLE ai.ai_authority_log RENAME COLUMN reason_code TO reason;
    """)
