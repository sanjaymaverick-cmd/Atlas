"""Persist one-time WebAuthn ceremony challenges.

Revision ID: 0002_webauthn_challenges
Revises: 0001_baseline
"""

from __future__ import annotations

from alembic import op

revision = "0002_webauthn_challenges"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity.webauthn_challenges (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID REFERENCES identity.users(id),
          ceremony_type TEXT NOT NULL
            CHECK (ceremony_type IN ('registration','authentication')),
          challenge TEXT NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          used_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_webauthn_challenges_expires
          ON identity.webauthn_challenges(expires_at)
          WHERE used_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE identity.webauthn_challenges")
