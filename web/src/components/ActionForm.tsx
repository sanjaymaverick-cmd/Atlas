import { useState, type FormEvent } from "react";

import { ApiError, request } from "../api/client";

// A declarative form for the API's many POST endpoints.
//
// Atlas exposes 104 POST endpoints against 11 GET ones, and most of the writes
// are the same shape: send a small JSON body to a path, get a record or an
// error envelope back. Describing those as data rather than hand-writing a
// hundred near-identical forms keeps them consistent and keeps the diff
// reviewable. Anything with genuinely bespoke behaviour — the document
// four-eyes export flow, say — is written out longhand instead.

export type FieldKind = "text" | "number" | "date" | "select" | "uuid";

export interface Field {
  name: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  options?: string[];
  placeholder?: string;
  help?: string;
  maxLength?: number;
}

export interface ActionFormProps {
  title: string;
  description?: string;
  /**
   * Built fresh on submit, from current scope and the entered values.
   *
   * Values are passed in because many endpoints identify their target in the
   * path, and most of those resources cannot be listed — so the id has to be
   * typed into the form and then lifted into the URL.
   */
  path: (values: Record<string, string>) => string;
  fields: Field[];
  /** Field names that build the path and must not be sent in the body. */
  pathFields?: string[];
  submitLabel: string;
  /** Values merged into the body that are not user-editable. */
  fixed?: Record<string, unknown>;
  onDone?: () => void;
  /** Blocks submission with this message when the scope is incomplete. */
  disabledReason?: string | null;
}

function coerce(field: Field, raw: string): unknown {
  if (raw === "") return null;
  if (field.kind === "number") {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : raw;
  }
  return raw;
}

export function ActionForm({
  title,
  description,
  path,
  fields,
  pathFields,
  submitLabel,
  fixed,
  onDone,
  disabledReason,
}: ActionFormProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const inPath = new Set(pathFields ?? []);
      const body: Record<string, unknown> = { ...fixed };
      for (const field of fields) {
        if (inPath.has(field.name)) continue;
        const value = coerce(field, values[field.name] ?? "");
        // Omit blanks entirely: several endpoints forbid unknown or null keys.
        if (value !== null) body[field.name] = value;
      }
      const created = await request<Record<string, unknown>>(path(values), {
        method: "POST",
        body,
      });
      const id = typeof created?.["id"] === "string" ? (created["id"] as string) : null;
      setResult(id ? `Done. New record ${id}` : "Done.");
      setValues({});
      onDone?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? `${caught.code}: ${caught.message}`
          : "The request could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <div>
        <h3>{title}</h3>
        {description && <p className="muted">{description}</p>}
      </div>

      {disabledReason && <p className="banner banner-info">{disabledReason}</p>}
      {error && <p className="banner banner-error">{error}</p>}
      {result && <p className="banner banner-ok">{result}</p>}

      {fields.length > 0 && (
        <div className="grid-2">
          {fields.map((field) => (
            <label className="field" key={field.name}>
              <span>
                {field.label} {!field.required && <em>optional</em>}
              </span>
              {field.kind === "select" ? (
                <select
                  required={field.required ?? false}
                  value={values[field.name] ?? ""}
                  onChange={(event) =>
                    setValues({ ...values, [field.name]: event.target.value })
                  }
                >
                  <option value="">—</option>
                  {(field.options ?? []).map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  required={field.required ?? false}
                  type={field.kind === "number" ? "number" : field.kind === "date" ? "date" : "text"}
                  step={field.kind === "number" ? "any" : undefined}
                  maxLength={field.maxLength}
                  spellCheck={field.kind === "uuid" ? false : undefined}
                  autoComplete="off"
                  placeholder={field.placeholder}
                  value={values[field.name] ?? ""}
                  onChange={(event) =>
                    setValues({ ...values, [field.name]: event.target.value })
                  }
                />
              )}
              {field.help && <span className="field-help">{field.help}</span>}
            </label>
          ))}
        </div>
      )}

      <div>
        <button className="btn btn-primary" disabled={busy || Boolean(disabledReason)}>
          {busy ? "Working…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
