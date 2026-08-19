import { useCallback, useEffect, useState } from "react";

import { ApiError, request } from "../api/client";
import type { Project, ProjectCreate } from "../api/types";

const ENTITY_KEY = "atlas.ui.legal_entity_id";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed)
    ? new Date(parsed).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : value;
}

export function ProjectsScreen() {
  // Projects are always read within a legal entity — there is no cross-entity
  // list endpoint, because authorisation is scoped per entity (Blueprint §15).
  const [entityId, setEntityId] = useState(() => localStorage.getItem(ENTITY_KEY) ?? "");
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ProjectCreate>({ name: "", code: "" });

  const load = useCallback(async (id: string) => {
    if (!id.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const found = await request<Project[]>(
        `/api/v1/legal-entities/${encodeURIComponent(id.trim())}/projects`,
      );
      setProjects(found);
    } catch (caught) {
      setProjects(null);
      setError(
        caught instanceof ApiError
          ? caught.status === 403
            ? "This session is not scoped to read projects for that legal entity."
            : caught.message
          : "Could not load projects.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (entityId) void load(entityId);
  }, [entityId, load]);

  function chooseEntity(event: React.FormEvent) {
    event.preventDefault();
    const form = new FormData(event.target as HTMLFormElement);
    const next = String(form.get("entity") ?? "").trim();
    localStorage.setItem(ENTITY_KEY, next);
    setEntityId(next);
  }

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await request<Project>(`/api/v1/legal-entities/${encodeURIComponent(entityId)}/projects`, {
        method: "POST",
        body: draft,
      });
      setDraft({ name: "", code: "" });
      setCreating(false);
      await load(entityId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the project.");
    }
  }

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
      await load(entityId);
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
        {entityId && (
          <button className="btn" onClick={() => setCreating((open) => !open)}>
            {creating ? "Cancel" : "New project"}
          </button>
        )}
      </header>

      <form onSubmit={chooseEntity} className="entity-bar">
        <label className="field field-inline">
          <span>Legal entity ID</span>
          <input
            name="entity"
            defaultValue={entityId}
            placeholder="00000000-0000-0000-0000-000000000000"
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        <button className="btn">Load</button>
      </form>

      {error && <p className="banner banner-error">{error}</p>}
      {notice && <p className="banner banner-ok">{notice}</p>}

      {creating && (
        <form onSubmit={createProject} className="card stack">
          <h3>New project</h3>
          <div className="grid-2">
            <label className="field">
              <span>Name</span>
              <input
                required
                maxLength={300}
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Code</span>
              <input
                required
                maxLength={100}
                value={draft.code}
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </label>
            <label className="field">
              <span>
                City <em>optional</em>
              </span>
              <input
                maxLength={200}
                value={draft.city ?? ""}
                onChange={(event) => setDraft({ ...draft, city: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Status</span>
              <select
                value={draft.status ?? "planning"}
                onChange={(event) => setDraft({ ...draft, status: event.target.value })}
              >
                <option value="planning">planning</option>
                <option value="active">active</option>
                <option value="on_hold">on_hold</option>
                <option value="completed">completed</option>
              </select>
            </label>
          </div>
          <div>
            <button className="btn btn-primary">Create project</button>
          </div>
        </form>
      )}

      {loading && <p className="muted">Loading…</p>}

      {!loading && projects !== null && projects.length === 0 && (
        <p className="empty">No projects for this legal entity yet.</p>
      )}

      {!loading && projects !== null && projects.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>City</th>
                <th>Status</th>
                <th>Target completion</th>
                <th>Ver.</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.name}</td>
                  <td className="mono">{project.code}</td>
                  <td>{project.city ?? "—"}</td>
                  <td>
                    <span className="pill">{project.status}</span>
                  </td>
                  <td>{formatDate(project.target_completion_date)}</td>
                  <td className="mono">{project.version}</td>
                  <td className="row-actions">
                    {/* Archival replaces deletion throughout Atlas; there is no delete. */}
                    <button className="btn btn-small" onClick={() => void archive(project)}>
                      Archive
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
