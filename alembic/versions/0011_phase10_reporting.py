"""Add Phase 10 separated reporting summary.

Revision ID: 0011_phase10_reporting
Revises: 0010_phase9_tally_reconciliation
"""

# ruff: noqa: E501
from __future__ import annotations

from alembic import op

revision = "0011_phase10_reporting"
down_revision = "0010_phase9_tally_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE reporting.report_requests (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), legal_entity_id UUID NOT NULL REFERENCES organization.legal_entities(id),
      project_id UUID REFERENCES organization.projects(id), report_type TEXT NOT NULL CHECK (report_type IN ('ceo_project_summary','ceo_entity_summary')),
      output_format TEXT NOT NULL CHECK (output_format IN ('pdf','xlsx')), status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','generating','ready','failed','expired')),
      output_document_id UUID REFERENCES documents.documents(id), requested_by UUID NOT NULL REFERENCES identity.users(id),
      requested_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      created_by UUID REFERENCES identity.users(id), updated_by UUID REFERENCES identity.users(id), version INTEGER NOT NULL DEFAULT 1,
      archived_at TIMESTAMPTZ, CHECK (project_id IS NOT NULL OR report_type = 'ceo_entity_summary'));
    CREATE INDEX idx_report_requests_scope_status ON reporting.report_requests(legal_entity_id, project_id, status);
    CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON reporting.report_requests FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    CREATE MATERIALIZED VIEW reporting.mv_ceo_project_summary AS
    WITH budget_totals AS (
      SELECT b.project_id, COALESCE(SUM(bl.planned_amount),0) planned_amount, COALESCE(SUM(bl.committed_amount),0) committed_amount, COALESCE(SUM(bl.actual_amount),0) actual_amount
      FROM budget.budgets b LEFT JOIN budget.budget_lines bl ON bl.budget_id=b.id AND bl.archived_at IS NULL
      WHERE b.archived_at IS NULL AND b.status IN ('approved','revised') GROUP BY b.project_id),
    po_totals AS (SELECT project_id, COALESCE(SUM(total_amount),0) approved_po_amount FROM procurement.purchase_orders WHERE archived_at IS NULL AND status IN ('approved','issued','partially_received','closed') GROUP BY project_id),
    payment_totals AS (SELECT project_id, COALESCE(SUM(amount),0) released_payment_amount FROM finance.payments WHERE status='released' GROUP BY project_id),
    collection_totals AS (SELECT b.project_id, COALESCE(SUM(c.amount) FILTER (WHERE c.status='allocated'),0) allocated_collection_amount, COUNT(*) FILTER (WHERE c.status='received') unallocated_collection_count
      FROM customers.bookings b JOIN customers.collections c ON c.booking_id=b.id AND c.archived_at IS NULL WHERE b.archived_at IS NULL AND b.status<>'cancelled' GROUP BY b.project_id),
    receivable_totals AS (SELECT b.project_id, COALESCE(SUM(pp.total_amount),0) scheduled_receivable_amount FROM customers.bookings b
      JOIN customers.payment_plans pp ON pp.booking_id=b.id AND pp.archived_at IS NULL AND pp.status='active' WHERE b.archived_at IS NULL AND b.status<>'cancelled' GROUP BY b.project_id),
    overdue_totals AS (SELECT b.project_id, COUNT(*) overdue_installment_count FROM customers.bookings b
      JOIN customers.payment_plans pp ON pp.booking_id=b.id AND pp.archived_at IS NULL AND pp.status='active'
      JOIN customers.payment_plan_installments i ON i.payment_plan_id=pp.id AND i.archived_at IS NULL AND i.status='overdue'
      WHERE b.archived_at IS NULL AND b.status<>'cancelled' GROUP BY b.project_id),
    delivery_risk AS (SELECT p.id project_id,
      (SELECT COUNT(*) FROM construction.schedule_activities a WHERE a.project_id=p.id AND a.archived_at IS NULL AND a.status='delayed') delayed_activity_count,
      (SELECT COUNT(*) FROM quality.inspections i WHERE i.project_id=p.id AND i.archived_at IS NULL AND i.status='completed' AND i.result='fail') failed_inspection_count,
      (SELECT COUNT(*) FROM compliance.compliance_obligations o WHERE o.project_id=p.id AND o.archived_at IS NULL AND o.status IN ('open','overdue')) open_compliance_count,
      (SELECT COUNT(*) FROM finance.reconciliations r WHERE r.legal_entity_id=p.legal_entity_id AND r.archived_at IS NULL AND r.status IN ('open','under_review')) open_reconciliation_count FROM organization.projects p),
    unit_totals AS (SELECT b.project_id, COUNT(u.id) total_unit_count, COUNT(*) FILTER (WHERE u.status='available') available_unit_count,
      COUNT(*) FILTER (WHERE u.status IN ('booked','sold','possessed')) committed_unit_count FROM organization.buildings b
      JOIN organization.floors f ON f.building_id=b.id JOIN organization.units u ON u.floor_id=f.id GROUP BY b.project_id)
    SELECT p.id project_id, p.legal_entity_id, COALESCE(bt.planned_amount,0)::NUMERIC(18,2) planned_amount,
      COALESCE(bt.committed_amount,0)::NUMERIC(18,2) committed_amount, COALESCE(bt.actual_amount,0)::NUMERIC(18,2) actual_amount,
      COALESCE(po.approved_po_amount,0)::NUMERIC(18,2) approved_po_amount, COALESCE(py.released_payment_amount,0)::NUMERIC(18,2) released_payment_amount,
      COALESCE(ct.allocated_collection_amount,0)::NUMERIC(18,2) allocated_collection_amount,
      GREATEST(COALESCE(rt.scheduled_receivable_amount,0)-COALESCE(ct.allocated_collection_amount,0),0)::NUMERIC(18,2) outstanding_receivable_amount,
      COALESCE(ct.unallocated_collection_count,0)::BIGINT unallocated_collection_count, COALESCE(ot.overdue_installment_count,0)::BIGINT overdue_installment_count,
      COALESCE(dr.delayed_activity_count,0)::BIGINT delayed_activity_count, COALESCE(dr.failed_inspection_count,0)::BIGINT failed_inspection_count,
      COALESCE(dr.open_compliance_count,0)::BIGINT open_compliance_count, COALESCE(dr.open_reconciliation_count,0)::BIGINT open_reconciliation_count,
      COALESCE(ut.total_unit_count,0)::BIGINT total_unit_count, COALESCE(ut.available_unit_count,0)::BIGINT available_unit_count,
      COALESCE(ut.committed_unit_count,0)::BIGINT committed_unit_count, statement_timestamp() refreshed_at
    FROM organization.projects p LEFT JOIN budget_totals bt ON bt.project_id=p.id LEFT JOIN po_totals po ON po.project_id=p.id
      LEFT JOIN payment_totals py ON py.project_id=p.id LEFT JOIN collection_totals ct ON ct.project_id=p.id
      LEFT JOIN receivable_totals rt ON rt.project_id=p.id LEFT JOIN overdue_totals ot ON ot.project_id=p.id
      LEFT JOIN delivery_risk dr ON dr.project_id=p.id LEFT JOIN unit_totals ut ON ut.project_id=p.id
    WHERE p.archived_at IS NULL WITH NO DATA;
    CREATE UNIQUE INDEX uq_mv_ceo_project_summary_project ON reporting.mv_ceo_project_summary(project_id);
    """)


def downgrade() -> None:
    op.execute(
        "DROP MATERIALIZED VIEW reporting.mv_ceo_project_summary; DROP TABLE reporting.report_requests"
    )
