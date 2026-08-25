import { ActionForm } from "../components/ActionForm";
import { formatAmount, formatDate } from "../components/DataTable";
import { ScopeBar } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { useResource } from "../hooks/useResource";
import type { EntityDashboard, ProjectDashboard } from "../api/types";

// Phase 10. These read through a separate reporting database — the API refuses
// to start unless ATLAS_REPORTING_DATABASE_URL names a different database from
// the transactional one — and return aggregates and opaque IDs only.

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "warn";
}) {
  return (
    <div className={tone === "warn" && Number(value) > 0 ? "metric metric-warn" : "metric"}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </div>
  );
}

export function DashboardScreen() {
  const { legalEntityId, projectId, project } = useScope();

  const entity = useResource<EntityDashboard>(
    legalEntityId.trim()
      ? `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/dashboard`
      : null,
  );
  const projectBoard = useResource<ProjectDashboard>(
    projectId ? `/api/v1/projects/${encodeURIComponent(projectId)}/dashboard` : null,
  );

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Dashboards</h2>
          <p className="muted">
            Aggregates from the reporting replica. No party, payment or document detail crosses
            this boundary.
          </p>
        </div>
      </header>

      <ScopeBar requireProject />

      {entity.error && <p className="banner banner-error">{entity.error}</p>}
      {entity.loading && <p className="muted">Loading entity dashboard…</p>}

      {entity.data && (
        <div className="card stack">
          <div>
            <h3>Legal entity</h3>
            <p className="muted">
              {entity.data.project_count} project(s) · refreshed {formatDate(entity.data.refreshed_at)}
            </p>
          </div>
          <div className="metrics">
            <Metric label="Planned" value={formatAmount(entity.data.planned_amount)} />
            <Metric label="Committed" value={formatAmount(entity.data.committed_amount)} />
            <Metric label="Actual" value={formatAmount(entity.data.actual_amount)} />
            <Metric label="Payments released" value={formatAmount(entity.data.released_payment_amount)} />
            <Metric label="Collections allocated" value={formatAmount(entity.data.allocated_collection_amount)} />
            <Metric label="Receivable outstanding" value={formatAmount(entity.data.outstanding_receivable_amount)} />
            <Metric label="Delayed activities" value={entity.data.delayed_activity_count} tone="warn" />
            <Metric label="Failed inspections" value={entity.data.failed_inspection_count} tone="warn" />
            <Metric label="Open compliance" value={entity.data.open_compliance_count} tone="warn" />
            <Metric label="Units available" value={entity.data.available_unit_count} />
          </div>
        </div>
      )}

      {projectBoard.error && <p className="banner banner-error">{projectBoard.error}</p>}

      {projectBoard.data && (
        <div className="card stack">
          <div>
            <h3>{project ? `${project.name} (${project.code})` : "Project"}</h3>
            <p className="muted">Refreshed {formatDate(projectBoard.data.refreshed_at)}</p>
          </div>
          <div className="metrics">
            <Metric label="Planned" value={formatAmount(projectBoard.data.planned_amount)} />
            <Metric label="Committed" value={formatAmount(projectBoard.data.committed_amount)} />
            <Metric label="Actual" value={formatAmount(projectBoard.data.actual_amount)} />
            <Metric label="Approved POs" value={formatAmount(projectBoard.data.approved_po_amount)} />
            <Metric label="Payments released" value={formatAmount(projectBoard.data.released_payment_amount)} />
            <Metric label="Receivable outstanding" value={formatAmount(projectBoard.data.outstanding_receivable_amount)} />
            <Metric label="Unallocated collections" value={projectBoard.data.unallocated_collection_count} tone="warn" />
            <Metric label="Overdue installments" value={projectBoard.data.overdue_installment_count} tone="warn" />
            <Metric label="Delayed activities" value={projectBoard.data.delayed_activity_count} tone="warn" />
            <Metric label="Failed inspections" value={projectBoard.data.failed_inspection_count} tone="warn" />
            <Metric label="Open compliance" value={projectBoard.data.open_compliance_count} tone="warn" />
            <Metric label="Open reconciliations" value={projectBoard.data.open_reconciliation_count} tone="warn" />
            <Metric label="Units total" value={projectBoard.data.total_unit_count} />
            <Metric label="Units available" value={projectBoard.data.available_unit_count} />
            <Metric label="Units committed" value={projectBoard.data.committed_unit_count} />
          </div>
        </div>
      )}

      <ActionForm
        title="Request a report"
        description="Queued for a controlled worker. Nothing is generated or sent from this request."
        path={() =>
          `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/report-requests`
        }
        fields={[
          {
            name: "report_type",
            label: "Report type",
            kind: "select",
            required: true,
            options: ["ceo_project_summary", "ceo_entity_summary"],
          },
          {
            name: "output_format",
            label: "Format",
            kind: "select",
            required: true,
            options: ["pdf", "xlsx"],
          },
        ]}
        fixed={projectId ? { project_id: projectId } : {}}
        submitLabel="Queue report"
        disabledReason={
          legalEntityId.trim() ? null : "Enter a legal entity ID above to request a report."
        }
      />
    </section>
  );
}
