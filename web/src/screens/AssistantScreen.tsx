import { useState, type FormEvent } from "react";

import { ApiError, request } from "../api/client";
import { ScopeBar } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";

// Phase 11. There is no inference provider: the Blueprint §25 hosting decision
// is still open, so the default provider fails closed with
// `hosting_not_configured`. This screen exists to make that boundary visible
// rather than to pretend an assistant exists.
//
// The two lists below are the real policy vocabulary from
// atlas/modules/ai_assistant/policy.py. Forbidden actions are offered
// deliberately: the refusal is the feature, and being able to see it refuse is
// worth more than hiding the option.

const INTENTS = ["information", "drafting", "recommendation", "workflow_assistance"];

const ALLOWED_ACTIONS = [
  "answer_question",
  "summarize_status",
  "compare_vendors",
  "draft_agreement",
  "draft_communication",
  "identify_missing_documents",
  "recommend_action",
  "calculate_scenario",
  "propose_task",
  "explain_risk",
  "flag_anomaly",
];

const FORBIDDEN_ACTIONS = [
  "approve_contract",
  "release_payment",
  "send_message",
  "modify_final_budget",
  "finalize_quantity",
  "change_drawing",
  "alter_permissions",
  "approve_device",
  "sign_document",
  "delete_record",
];

export function AssistantScreen() {
  const { legalEntityId, projectId } = useScope();
  const [query, setQuery] = useState("");
  const [intent, setIntent] = useState("information");
  const [action, setAction] = useState("answer_question");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<{ kind: "ok" | "refused"; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setOutcome(null);
    try {
      const body: Record<string, unknown> = {
        query,
        intent,
        proposed_action: action,
        ...(legalEntityId.trim() ? { legal_entity_id: legalEntityId.trim() } : {}),
        ...(projectId ? { project_id: projectId } : {}),
      };
      const response = await request<Record<string, unknown>>("/api/v1/assistant/queries", {
        method: "POST",
        body,
      });
      setOutcome({ kind: "ok", text: JSON.stringify(response, null, 2) });
    } catch (caught) {
      setOutcome(
        caught instanceof ApiError
          ? { kind: "refused", text: `${caught.code}: ${caught.message}` }
          : { kind: "refused", text: "The request could not be completed." },
      );
    } finally {
      setBusy(false);
    }
  }

  const forbidden = FORBIDDEN_ACTIONS.includes(action);

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Assistant</h2>
          <p className="muted">A safety boundary, not a working assistant.</p>
        </div>
      </header>

      <p className="banner banner-info">
        No model, vendor, endpoint or API key has been selected — the Blueprint §25 hosting
        decision is still open, so the provider fails closed with{" "}
        <code>hosting_not_configured</code>. Authority policy, prompt-injection refusal and
        confidence gating are implemented and enforced regardless.
      </p>

      <ScopeBar requireProject />

      <form className="card stack" onSubmit={submit}>
        <label className="field">
          <span>Query</span>
          <input
            required
            maxLength={12000}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Summarise the open compliance obligations for this project"
          />
        </label>

        <div className="grid-2">
          <label className="field">
            <span>Intent</span>
            <select value={intent} onChange={(event) => setIntent(event.target.value)}>
              {INTENTS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Proposed action</span>
            <select value={action} onChange={(event) => setAction(event.target.value)}>
              <optgroup label="Permitted">
                {ALLOWED_ACTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Permanently forbidden">
                {FORBIDDEN_ACTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>

        {forbidden && (
          <p className="banner banner-error">
            This action is on the permanent forbidden list. No authority level unlocks it, and no
            configuration change will — the assistant may never approve, pay, send, sign or delete.
            Submitting will be refused, which is the point.
          </p>
        )}

        <div>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Evaluating…" : "Evaluate"}
          </button>
        </div>

        {outcome && (
          <pre className={outcome.kind === "ok" ? "code" : "code code-error"}>{outcome.text}</pre>
        )}
      </form>
    </section>
  );
}
