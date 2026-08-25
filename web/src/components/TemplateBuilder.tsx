import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, request } from "../api/client";

interface ChecklistItem {
  item: string;
  requires_evidence: boolean;
}

interface TemplateDraft {
  id: string;
  project_id: string;
  work_package: string;
  template_name: string;
  checklist: ChecklistItem[];
  status: "draft";
  version: number;
}

const emptyItem = (): ChecklistItem => ({ item: "", requires_evidence: false });

function errorMessage(caught: unknown): string {
  return caught instanceof ApiError
    ? `${caught.code}: ${caught.message}`
    : "The template operation could not be completed.";
}

export function TemplateBuilder({ projectId }: { projectId: string }) {
  const [drafts, setDrafts] = useState<TemplateDraft[]>([]);
  const [selected, setSelected] = useState<TemplateDraft | null>(null);
  const [workPackage, setWorkPackage] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [items, setItems] = useState<ChecklistItem[]>([emptyItem()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) {
      setDrafts([]);
      return;
    }
    try {
      setDrafts(
        await request<TemplateDraft[]>(
          `/api/v1/projects/${encodeURIComponent(projectId)}/inspection-template-drafts`,
        ),
      );
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [projectId]);

  useEffect(() => {
    setSelected(null);
    setWorkPackage("");
    setTemplateName("");
    setItems([emptyItem()]);
    setError(null);
    setNotice(null);
    void load();
  }, [load]);

  function reset() {
    setSelected(null);
    setWorkPackage("");
    setTemplateName("");
    setItems([emptyItem()]);
  }

  function edit(draft: TemplateDraft) {
    setSelected(draft);
    setWorkPackage(draft.work_package);
    setTemplateName(draft.template_name);
    setItems(draft.checklist.map((item) => ({ ...item })));
    setError(null);
    setNotice(null);
  }

  function updateItem(index: number, patch: Partial<ChecklistItem>) {
    setItems(items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const checklist = items.map((item) => ({ ...item, item: item.item.trim() }));
      if (checklist.some((item) => !item.item)) {
        setError("Every checklist row needs a description.");
        return;
      }
      if (selected) {
        await request(`/api/v1/inspection-templates/${encodeURIComponent(selected.id)}`, {
          method: "PUT",
          body: {
            work_package: workPackage.trim(),
            template_name: templateName.trim(),
            checklist,
            expected_version: selected.version,
          },
        });
        setNotice("Draft updated.");
      } else {
        await request("/api/v1/inspection-templates", {
          method: "POST",
          body: {
            project_id: projectId,
            work_package: workPackage.trim(),
            template_name: templateName.trim(),
            checklist,
          },
        });
        setNotice("Draft created.");
      }
      reset();
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function activate(draft: TemplateDraft) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await request(`/api/v1/inspection-templates/${encodeURIComponent(draft.id)}/transition`, {
        method: "POST",
        body: { target_status: "active" },
      });
      if (selected?.id === draft.id) reset();
      setNotice("Template activated. Active templates cannot be edited in the builder.");
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-labelledby="template-builder-title">
      <div className="page-head">
        <div>
          <h3 id="template-builder-title">QA/QC template builder</h3>
          <p className="muted">
            Build a project checklist without JSON. Only drafts are editable; activation makes the
            checklist available to inspections.
          </p>
        </div>
        {selected && (
          <button className="btn" type="button" onClick={reset} disabled={busy}>
            New draft
          </button>
        )}
      </div>

      {!projectId && <p className="banner banner-info">Select a project to manage templates.</p>}
      {error && <p className="banner banner-error">{error}</p>}
      {notice && <p className="banner banner-ok">{notice}</p>}

      {drafts.length > 0 && (
        <div className="stack">
          <h4>Project drafts</h4>
          {drafts.map((draft) => (
            <div className="template-draft-row" key={draft.id}>
              <div>
                <strong>{draft.template_name}</strong>
                <span className="muted">
                  {draft.work_package} · {draft.checklist.length} items · version {draft.version}
                </span>
              </div>
              <div className="button-row">
                <button className="btn" type="button" onClick={() => edit(draft)} disabled={busy}>
                  Edit
                </button>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={() => void activate(draft)}
                  disabled={busy}
                >
                  Activate
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <form className="stack" onSubmit={save}>
        <div className="grid-2">
          <label className="field">
            <span>Work package</span>
            <input
              required
              maxLength={200}
              value={workPackage}
              onChange={(event) => setWorkPackage(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Template name</span>
            <input
              required
              maxLength={300}
              value={templateName}
              onChange={(event) => setTemplateName(event.target.value)}
            />
          </label>
        </div>

        <div className="stack">
          <div className="page-head">
            <h4>Checklist</h4>
            <button
              className="btn"
              type="button"
              onClick={() => setItems([...items, emptyItem()])}
              disabled={busy || items.length >= 200}
            >
              Add item
            </button>
          </div>
          {items.map((item, index) => (
            <div className="checklist-editor-row" key={index}>
              <label className="field checklist-editor-text">
                <span>Item {index + 1}</span>
                <input
                  required
                  maxLength={500}
                  value={item.item}
                  onChange={(event) => updateItem(index, { item: event.target.value })}
                />
              </label>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={item.requires_evidence}
                  onChange={(event) =>
                    updateItem(index, { requires_evidence: event.target.checked })
                  }
                />
                Evidence required
              </label>
              <button
                className="btn btn-danger"
                type="button"
                disabled={busy || items.length === 1}
                onClick={() => setItems(items.filter((_, itemIndex) => itemIndex !== index))}
              >
                Remove
              </button>
            </div>
          ))}
        </div>

        <div>
          <button className="btn btn-primary" disabled={busy || !projectId}>
            {busy ? "Saving…" : selected ? "Update draft" : "Create draft"}
          </button>
        </div>
      </form>
    </section>
  );
}
