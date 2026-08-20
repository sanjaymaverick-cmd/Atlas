import { useState } from "react";

import { ActionForm } from "../components/ActionForm";
import { RegisterTable } from "../components/RegisterTable";
import { ScopeBar } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { CATALOG, type Workflow } from "../workflows/catalog";
import { REGISTERS } from "../workflows/registers";

// Registers and operations for the six modules that were write-only until the
// read endpoints landed on 2026-08-20. Each phase shows what exists, then what
// can be done to it.

export function WorkflowsScreen() {
  const { legalEntityId, projectId } = useScope();
  const [groupIndex, setGroupIndex] = useState(0);
  const [showActions, setShowActions] = useState(false);
  const group = CATALOG[groupIndex];
  const scope = {
    entity: encodeURIComponent(legalEntityId.trim()),
    project: encodeURIComponent(projectId),
  };

  function blockedReason(workflow: Workflow): string | null {
    if (workflow.scope === "entity" && !legalEntityId.trim()) {
      return "Enter a legal entity ID above to use this.";
    }
    if (workflow.scope === "project" && !projectId) {
      return "Select a project above to use this.";
    }
    return null;
  }

  const registers = group ? (REGISTERS[group.phase] ?? []) : [];

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Workflows</h2>
          <p className="muted">Registers and operations, by phase.</p>
        </div>
      </header>

      <ScopeBar requireProject />

      <div className="tabs tabs-wrap" role="tablist">
        {CATALOG.map((entry, index) => (
          <button
            key={entry.phase}
            role="tab"
            aria-selected={index === groupIndex}
            className={index === groupIndex ? "tab tab-active" : "tab"}
            onClick={() => {
              setGroupIndex(index);
              setShowActions(false);
            }}
          >
            {entry.phase} · {entry.title}
          </button>
        ))}
      </div>

      {group && (
        <>
          <p className="muted">{group.blurb}</p>

          {registers.map((register) => (
            <RegisterTable
              key={register.key}
              register={register}
              scope={scope}
              blocked={null}
            />
          ))}

          <div className="page-head">
            <h3>Operations</h3>
            <button className="btn" onClick={() => setShowActions((open) => !open)}>
              {showActions ? "Hide" : `Show ${group.workflows.length} operations`}
            </button>
          </div>

          {showActions && (
            <div className="stack">
              <p className="banner banner-info">
                Actions that target an existing record still ask for its ID. The registers above
                list them, and detail endpoints — <code>GET /ncrs/{"{id}"}</code> and the like —
                do not exist yet, so a row cannot yet be clicked through to its own page.
              </p>
              {group.workflows.map((workflow) => (
                <ActionForm
                  key={workflow.key}
                  title={workflow.title}
                  {...(workflow.description ? { description: workflow.description } : {})}
                  path={(values) => workflow.path(scope, values)}
                  fields={workflow.fields}
                  {...(workflow.pathFields ? { pathFields: workflow.pathFields } : {})}
                  submitLabel={workflow.submitLabel}
                  disabledReason={blockedReason(workflow)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
