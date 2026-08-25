import { useState } from "react";

import { ActionForm } from "../components/ActionForm";
import { DataTable, Pill, formatAmount, type Column } from "../components/DataTable";
import { ScopeBar, scopeGuard } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { useResource } from "../hooks/useResource";
import type { LandParcel } from "../api/types";

// Phase 3. Land parcels are readable; due-diligence items, legal approvals and
// loans are write-only in the API, so they appear here as actions against a
// selected parcel rather than as lists.

const ACQUISITION_STATUSES = [
  "identified",
  "due_diligence",
  "under_negotiation",
  "acquired",
  "dropped",
];

const columns: Column<LandParcel>[] = [
  { header: "Survey no.", cell: (p) => p.survey_number ?? "—", mono: true },
  { header: "Location", cell: (p) => p.location ?? "—" },
  { header: "Area (sqft)", cell: (p) => formatAmount(p.area_sqft), align: "right" },
  { header: "Acquisition", cell: (p) => <Pill>{p.acquisition_status}</Pill> },
  { header: "Ver.", cell: (p) => p.version, mono: true, align: "right" },
];

export function LandScreen() {
  const { legalEntityId, projectId } = useScope();
  const [selected, setSelected] = useState<LandParcel | null>(null);

  const guard = scopeGuard(legalEntityId, projectId, false);
  const parcels = useResource<LandParcel[]>(
    legalEntityId.trim()
      ? `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/land-parcels`
      : null,
  );

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Land</h2>
          <p className="muted">Parcels, due diligence and acquisition lifecycle.</p>
        </div>
      </header>

      <ScopeBar />
      {guard && <p className="banner banner-info">{guard}</p>}
      {parcels.error && <p className="banner banner-error">{parcels.error}</p>}
      {parcels.loading && <p className="muted">Loading…</p>}

      {parcels.data && (
        <DataTable
          rows={parcels.data}
          columns={columns}
          rowKey={(p) => p.id}
          empty="No land parcels for this legal entity."
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
        title="Register a land parcel"
        path={() =>
          `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/land-parcels`
        }
        fields={[
          { name: "survey_number", label: "Survey number", kind: "text" },
          { name: "location", label: "Location", kind: "text" },
          { name: "area_sqft", label: "Area (sqft)", kind: "number" },
        ]}
        fixed={projectId ? { project_id: projectId } : {}}
        submitLabel="Register parcel"
        onDone={() => void parcels.reload()}
        disabledReason={guard}
      />

      {selected && (
        <>
          <ActionForm
            title={`Move acquisition status — ${selected.survey_number ?? selected.id.slice(0, 8)}`}
            description="Invalid jumps are rejected as conflicts, not silently applied."
            path={() => `/api/v1/land-parcels/${encodeURIComponent(selected.id)}/transition`}
            fields={[
              {
                name: "target_status",
                label: "Target status",
                kind: "select",
                required: true,
                options: ACQUISITION_STATUSES,
              },
            ]}
            submitLabel="Apply transition"
            onDone={() => void parcels.reload()}
          />

          <ActionForm
            title="Add a due-diligence item"
            description="Evidence must point at a controlled Documents record, never a file path."
            path={() => `/api/v1/land-parcels/${encodeURIComponent(selected.id)}/due-diligence`}
            fields={[
              { name: "category", label: "Category", kind: "text", required: true },
              { name: "title", label: "Title", kind: "text", required: true },
              {
                name: "evidence_document_id",
                label: "Evidence document ID",
                kind: "uuid",
                placeholder: "00000000-0000-0000-0000-000000000000",
              },
              { name: "notes", label: "Notes", kind: "text" },
            ]}
            submitLabel="Add item"
          />

          <ActionForm
            title="Record a legal approval"
            path={() => `/api/v1/land-parcels/${encodeURIComponent(selected.id)}/legal-approvals`}
            fields={[
              { name: "approval_type", label: "Approval type", kind: "text", required: true },
              { name: "authority", label: "Authority", kind: "text" },
              { name: "reference_number", label: "Reference number", kind: "text" },
            ]}
            submitLabel="Record approval"
          />
        </>
      )}
    </section>
  );
}
