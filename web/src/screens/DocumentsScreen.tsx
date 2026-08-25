import { useState } from "react";

import { ActionForm } from "../components/ActionForm";
import { DataTable, Pill, formatDate, type Column } from "../components/DataTable";
import { ScopeBar, scopeGuard } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { useResource } from "../hooks/useResource";
import type { AtlasDocument, DocumentRevision } from "../api/types";

// Phase 2. Documents are one of the few modules with real read endpoints, so
// this screen can show a register and drill into revisions.
//
// Deliberately not built here: binary revision intake, watermarked preview and
// the four-eyes export flow. Those need file upload, a sandboxed viewer and a
// fresh passkey step-up, and doing them badly would be worse than not at all —
// an export is a controlled release of confidential material.

const REVISION_STATUSES = [
  "draft",
  "virus_scanned",
  "quarantined",
  "under_review",
  "approved",
  "issued",
  "superseded",
];

const documentColumns: Column<AtlasDocument>[] = [
  { header: "Drawing no.", cell: (d) => d.drawing_number ?? "—", mono: true },
  { header: "Discipline", cell: (d) => d.discipline ?? "—" },
  { header: "Type", cell: (d) => d.document_type ?? "—" },
  { header: "Classification", cell: (d) => <Pill>{d.classification}</Pill> },
  { header: "Status", cell: (d) => <Pill>{d.status}</Pill> },
  { header: "Ver.", cell: (d) => d.version, mono: true, align: "right" },
];

const revisionColumns: Column<DocumentRevision>[] = [
  { header: "Rev.", cell: (r) => r.revision_code, mono: true },
  { header: "Purpose", cell: (r) => r.issue_purpose ?? "—" },
  { header: "Issued", cell: (r) => formatDate(r.issue_date) },
  { header: "Status", cell: (r) => <Pill>{r.status}</Pill> },
  { header: "Checksum", cell: (r) => r.checksum_sha256.slice(0, 12), mono: true },
  { header: "Created", cell: (r) => formatDate(r.created_at) },
];

export function DocumentsScreen() {
  const { legalEntityId, projectId } = useScope();
  const [openDocument, setOpenDocument] = useState<AtlasDocument | null>(null);

  const guard = scopeGuard(legalEntityId, projectId, true);
  const documents = useResource<AtlasDocument[]>(
    projectId ? `/api/v1/projects/${encodeURIComponent(projectId)}/documents` : null,
  );
  const revisions = useResource<DocumentRevision[]>(
    openDocument ? `/api/v1/documents/${encodeURIComponent(openDocument.id)}/revisions` : null,
  );

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Documents</h2>
          <p className="muted">Drawing and document register, with immutable revisions.</p>
        </div>
      </header>

      <ScopeBar requireProject />
      {guard && <p className="banner banner-info">{guard}</p>}
      {documents.error && <p className="banner banner-error">{documents.error}</p>}
      {documents.loading && <p className="muted">Loading…</p>}

      {documents.data && (
        <DataTable
          rows={documents.data}
          columns={documentColumns}
          rowKey={(d) => d.id}
          empty="No documents registered for this project."
          actions={(row) => (
            <button
              className="btn btn-small"
              onClick={() => setOpenDocument(openDocument?.id === row.id ? null : row)}
            >
              {openDocument?.id === row.id ? "Hide revisions" : "Revisions"}
            </button>
          )}
        />
      )}

      {openDocument && (
        <div className="card stack">
          <div>
            <h3>Revisions — {openDocument.drawing_number ?? openDocument.id.slice(0, 8)}</h3>
            <p className="muted">
              Revisions are immutable. A new one supersedes its predecessor rather than replacing
              it.
            </p>
          </div>
          {revisions.error && <p className="banner banner-error">{revisions.error}</p>}
          {revisions.data && (
            <DataTable
              rows={revisions.data}
              columns={revisionColumns}
              rowKey={(r) => r.id}
              empty="No revisions on this document yet."
            />
          )}
        </div>
      )}

      <ActionForm
        title="Register a document"
        description="Creates the register entry. Binary content is added as a revision."
        path={() => `/api/v1/projects/${encodeURIComponent(projectId)}/documents`}
        fields={[
          { name: "drawing_number", label: "Drawing number", kind: "text", maxLength: 100 },
          { name: "discipline", label: "Discipline", kind: "text", maxLength: 100 },
          { name: "document_type", label: "Document type", kind: "text", maxLength: 100 },
          {
            name: "classification",
            label: "Classification",
            kind: "select",
            options: ["internal", "confidential", "restricted"],
            help: "Restricted is required for anything holding KYC or payment evidence.",
          },
        ]}
        submitLabel="Register document"
        onDone={() => void documents.reload()}
        disabledReason={guard}
      />

      {openDocument && (
        <ActionForm
          title="Add a revision"
          description="Metadata only. The object storage key must already hold the verified content."
          path={() => `/api/v1/documents/${encodeURIComponent(openDocument.id)}/revisions`}
          fields={[
            { name: "revision_code", label: "Revision code", kind: "text", required: true },
            { name: "object_storage_key", label: "Object storage key", kind: "text", required: true },
            {
              name: "checksum_sha256",
              label: "SHA-256 checksum",
              kind: "text",
              required: true,
              help: "64 lowercase hex characters; the database rejects anything else.",
            },
            { name: "issue_purpose", label: "Issue purpose", kind: "text" },
            { name: "issue_date", label: "Issue date", kind: "date" },
          ]}
          submitLabel="Add revision"
          onDone={() => void revisions.reload()}
        />
      )}

      {openDocument && revisions.data && revisions.data.length > 0 && (
        <ActionForm
          title="Transition a revision"
          description="Lifecycle moves are ordered; invalid jumps are rejected as conflicts."
          path={() => `/api/v1/document-revisions/${encodeURIComponent(revisionTarget(revisions.data))}/transition`}
          fields={[
            {
              name: "target_status",
              label: "Target status",
              kind: "select",
              required: true,
              options: REVISION_STATUSES,
            },
          ]}
          submitLabel="Apply transition"
          onDone={() => void revisions.reload()}
          disabledReason={null}
        />
      )}
    </section>
  );
}

/** The newest revision is the one a lifecycle action almost always targets. */
function revisionTarget(revisions: DocumentRevision[] | null): string {
  return revisions && revisions.length > 0 ? (revisions[revisions.length - 1]?.id ?? "") : "";
}
