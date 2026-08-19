import { useState } from "react";

import { ApiError, request } from "../api/client";
import { ActionForm } from "../components/ActionForm";
import { DataTable, Pill, formatDate, type Column } from "../components/DataTable";
import { ScopeBar, scopeGuard } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import type { Project } from "../api/types";

const columns: Column<Project>[] = [
  { header: "Name", cell: (p) => p.name },
  { header: "Code", cell: (p) => p.code, mono: true },
  { header: "City", cell: (p) => p.city ?? "—" },
  { header: "Status", cell: (p) => <Pill>{p.status}</Pill> },
  { header: "Target completion", cell: (p) => formatDate(p.target_completion_date) },
  { header: "Ver.", cell: (p) => p.version, mono: true, align: "right" },
];

export function ProjectsScreen() {
  const { legalEntityId, projects, projectsError, loadingProjects, refreshProjects } = useScope();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const guard = scopeGuard(legalEntityId, "", false);

  async function archive(project: Project) {
    setError(null);
    setNotice(null);
    try {
      await request<Project>(`/api/v1/projects/${project.id}/archive`, { method: "POST" });
      // The list endpoint returns live projects only, so the row disappears
      // rather than reappearing flagged. Say so, because a row vanishing after
      // a click otherwise reads as a delete — and Atlas never deletes.
      setNotice(
        `${project.name} was archived. Archived projects are hidden from this list but are retained, and remain retrievable by ID.`,
      );
      await refreshProjects();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not archive the project.");
    }
  }

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Projects</h2>
          <p className="muted">Scoped to one legal entity.</p>
        </div>
      </header>

      <ScopeBar />
      {guard && <p className="banner banner-info">{guard}</p>}
      {projectsError && <p className="banner banner-error">{projectsError}</p>}
      {error && <p className="banner banner-error">{error}</p>}
      {notice && <p className="banner banner-ok">{notice}</p>}
      {loadingProjects && <p className="muted">Loading…</p>}

      {!loadingProjects && legalEntityId.trim() !== "" && (
        <DataTable
          rows={projects}
          columns={columns}
          rowKey={(p) => p.id}
          empty="No projects for this legal entity yet."
          actions={(row) => (
            /* Archival replaces deletion throughout Atlas; there is no delete. */
            <button className="btn btn-small" onClick={() => void archive(row)}>
              Archive
            </button>
          )}
        />
      )}

      <ActionForm
        title="New project"
        path={() => `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/projects`}
        fields={[
          { name: "name", label: "Name", kind: "text", required: true, maxLength: 300 },
          { name: "code", label: "Code", kind: "text", required: true, maxLength: 100 },
          { name: "city", label: "City", kind: "text", maxLength: 200 },
          {
            name: "status",
            label: "Status",
            kind: "select",
            options: ["planning", "active", "on_hold", "completed"],
          },
          { name: "start_date", label: "Start date", kind: "date" },
          { name: "target_completion_date", label: "Target completion", kind: "date" },
        ]}
        submitLabel="Create project"
        onDone={() => void refreshProjects()}
        disabledReason={guard}
      />
    </section>
  );
}
