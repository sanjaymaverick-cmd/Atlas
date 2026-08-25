"""Enforce Phase 7 workflow and controlled-evidence integrity.

Revision ID: 0017_phase7_workflow_integrity
Revises: 0016_phase6_bim_mapping
"""

from __future__ import annotations

from alembic import op

revision = "0017_phase7_workflow_integrity"
down_revision = "0016_phase6_bim_mapping"
branch_labels = None
depends_on = None


_CHANGE_STATUSES = (
    "'requested','feasibility_review','structural_review','revised_drawings',"
    "'quantity_impact','budget_impact','procurement_impact','contract_impact',"
    "'schedule_impact','customer_impact','commercial_quotation','approved',"
    "'implemented','verified','closed','rejected'"
)


def _add_constraint_if_missing(table: str, name: str, ddl: str) -> None:
    op.execute(
        f"""DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = '{name}' AND conrelid = '{table}'::regclass
          ) THEN
            ALTER TABLE {table} ADD CONSTRAINT {name} {ddl};
          END IF;
        END
        $$"""  # noqa: S608 - identifiers are module-owned migration constants
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE construction.change_requests "
        "DROP CONSTRAINT change_requests_status_check, "
        f"ADD CONSTRAINT change_requests_status_check CHECK (status IN ({_CHANGE_STATUSES}))"
    )
    for table, old_constraint, new_constraint in (
        (
            "construction.change_requests",
            "change_requests_evidence_document_id_fkey",
            "fk_change_evidence_project",
        ),
        ("quality.rfis", "rfis_evidence_document_id_fkey", "fk_rfi_evidence_project"),
        ("quality.ncrs", "ncrs_evidence_document_id_fkey", "fk_ncr_evidence_project"),
        (
            "quality.discrepancy_cases",
            "discrepancy_cases_evidence_document_id_fkey",
            "fk_discrepancy_evidence_project",
        ),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {old_constraint}")
        _add_constraint_if_missing(
            table,
            new_constraint,
            "FOREIGN KEY (evidence_document_id, project_id) "
            "REFERENCES documents.documents(id, project_id)",
        )


def downgrade() -> None:
    for table, old_constraint, new_constraint in (
        (
            "construction.change_requests",
            "change_requests_evidence_document_id_fkey",
            "fk_change_evidence_project",
        ),
        ("quality.rfis", "rfis_evidence_document_id_fkey", "fk_rfi_evidence_project"),
        ("quality.ncrs", "ncrs_evidence_document_id_fkey", "fk_ncr_evidence_project"),
        (
            "quality.discrepancy_cases",
            "discrepancy_cases_evidence_document_id_fkey",
            "fk_discrepancy_evidence_project",
        ),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {new_constraint}")
        _add_constraint_if_missing(
            table,
            old_constraint,
            "FOREIGN KEY (evidence_document_id) REFERENCES documents.documents(id)",
        )
    op.execute(
        "ALTER TABLE construction.change_requests "
        "DROP CONSTRAINT change_requests_status_check, "
        "ADD CONSTRAINT change_requests_status_check CHECK (status IN ("
        "'requested','feasibility_review','structural_review','revised_drawings',"
        "'quantity_impact','budget_impact','procurement_impact','contract_impact',"
        "'commercial_quotation','approved','implemented','verified','closed','rejected'))"
    )
