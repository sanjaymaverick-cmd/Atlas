"""Enforce Phase 8 booking evidence project scope.

Revision ID: 0018_phase8_customer_integrity
Revises: 0017_phase7_workflow_integrity
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "0018_phase8_customer_integrity"
down_revision = "0017_phase7_workflow_integrity"
branch_labels = None
depends_on = None


def _constraint_exists(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name})
        .scalar()
    )


def upgrade() -> None:
    if _constraint_exists("bookings_booking_document_id_fkey"):
        op.execute(
            "ALTER TABLE customers.bookings DROP CONSTRAINT bookings_booking_document_id_fkey"
        )
    if not _constraint_exists("fk_bookings_document_project"):
        op.execute(
            "ALTER TABLE customers.bookings ADD CONSTRAINT fk_bookings_document_project "
            "FOREIGN KEY (booking_document_id, project_id) "
            "REFERENCES documents.documents(id, project_id)"
        )


def downgrade() -> None:
    if _constraint_exists("fk_bookings_document_project"):
        op.execute("ALTER TABLE customers.bookings DROP CONSTRAINT fk_bookings_document_project")
    if not _constraint_exists("bookings_booking_document_id_fkey"):
        op.execute(
            "ALTER TABLE customers.bookings ADD CONSTRAINT bookings_booking_document_id_fkey "
            "FOREIGN KEY (booking_document_id) REFERENCES documents.documents(id)"
        )
