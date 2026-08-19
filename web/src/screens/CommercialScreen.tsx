import { useState } from "react";

import { ActionForm } from "../components/ActionForm";
import { DataTable, Pill, formatAmount, formatDate, type Column } from "../components/DataTable";
import { ScopeBar, scopeGuard } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { useResource } from "../hooks/useResource";
import type { Budget } from "../api/types";

// Phase 4. Budgets are the only readable resource in this module; purchase
// orders, contracts, vendor onboarding, KYC, insurance and labour compliance
// are write-only in the API, so they appear as actions rather than registers.
//
// Note the rule that no schema constraint enforces: a purchase order cannot be
// issued until its vendor is active. That is application-layer by design
// (Blueprint §11), so the API will refuse the transition rather than the
// database refusing the row.

const BUDGET_STATUSES = ["draft", "submitted", "approved", "revised"];

const columns: Column<Budget>[] = [
  { header: "Budget", cell: (b) => b.id.slice(0, 8), mono: true },
  { header: "Total", cell: (b) => formatAmount(b.total_amount), align: "right" },
  { header: "Status", cell: (b) => <Pill>{b.status}</Pill> },
  { header: "Approved", cell: (b) => formatDate(b.approved_at) },
  { header: "Ver.", cell: (b) => b.version, mono: true, align: "right" },
];

export function CommercialScreen() {
  const { legalEntityId, projectId } = useScope();
  const [selected, setSelected] = useState<Budget | null>(null);

  const guard = scopeGuard(legalEntityId, projectId, true);
  const budgets = useResource<Budget[]>(
    projectId ? `/api/v1/projects/${encodeURIComponent(projectId)}/budgets` : null,
  );

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Commercial</h2>
          <p className="muted">Budgets, procurement and vendor onboarding.</p>
        </div>
      </header>

      <ScopeBar requireProject />
      {guard && <p className="banner banner-info">{guard}</p>}
      {budgets.error && <p className="banner banner-error">{budgets.error}</p>}
      {budgets.loading && <p className="muted">Loading…</p>}

      {budgets.data && (
        <DataTable
          rows={budgets.data}
          columns={columns}
          rowKey={(b) => b.id}
          empty="No budgets for this project."
          actions={(row) => (
            <button
              className="btn btn-small"
              onClick={() => setSelected(selected?.id === row.id ? null : row)}
            >
              {selected?.id === row.id ? "Close" : "Actions"}
            </button>
          )}
        />
      )}

      <ActionForm
        title="Create a budget"
        path={() => `/api/v1/projects/${encodeURIComponent(projectId)}/budgets`}
        fields={[{ name: "total_amount", label: "Total amount", kind: "number", required: true }]}
        fixed={{ legal_entity_id: legalEntityId.trim() }}
        submitLabel="Create budget"
        onDone={() => void budgets.reload()}
        disabledReason={guard}
      />

      {selected && (
        <>
          <ActionForm
            title="Add a budget line"
            path={() => `/api/v1/budgets/${encodeURIComponent(selected.id)}/lines`}
            fields={[
              { name: "description", label: "Description", kind: "text", required: true },
              { name: "planned_amount", label: "Planned amount", kind: "number", required: true },
            ]}
            submitLabel="Add line"
          />
          <ActionForm
            title="Move budget status"
            path={() => `/api/v1/budgets/${encodeURIComponent(selected.id)}/transition`}
            fields={[
              {
                name: "target_status",
                label: "Target status",
                kind: "select",
                required: true,
                options: BUDGET_STATUSES,
              },
            ]}
            submitLabel="Apply transition"
            onDone={() => void budgets.reload()}
          />
        </>
      )}

      <ActionForm
        title="Raise a purchase order"
        description="The order cannot be issued until its vendor is active — the API enforces that, not the schema."
        path={() => `/api/v1/projects/${encodeURIComponent(projectId)}/purchase-orders`}
        fields={[
          { name: "vendor_id", label: "Vendor ID", kind: "uuid", required: true },
          { name: "total_amount", label: "Total amount", kind: "number", required: true },
        ]}
        submitLabel="Raise order"
        disabledReason={guard}
      />

      <ActionForm
        title="Start vendor onboarding"
        description="One onboarding record per vendor; a second is rejected by the database."
        path={() => `/api/v1/vendors/${encodeURIComponent("VENDOR_ID")}/onboarding`}
        fields={[]}
        submitLabel="Not available here"
        disabledReason="Vendor onboarding needs a vendor ID, and no endpoint lists vendors. Use the API directly until a vendor register exists."
      />
    </section>
  );
}
