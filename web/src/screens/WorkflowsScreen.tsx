import { useState } from "react";

import { ActionForm } from "../components/ActionForm";
import { ScopeBar } from "../components/ScopeBar";
import { useScope } from "../context/ScopeContext";
import { CATALOG, type Workflow } from "../workflows/catalog";

// Every write the API offers for the modules that expose no reads.
//
// This screen is shaped by an API limitation, and says so plainly rather than
// papering over it: six of Atlas's modules have no GET endpoints, so there is
// no register to browse and no row to click. Actions that target an existing
// record therefore ask for its UUID.

export function WorkflowsScreen() {
  const { legalEntityId, projectId } = useScope();
  const [groupIndex, setGroupIndex] = useState(0);
  const group = CATALOG[groupIndex];

  function blockedReason(workflow: Workflow): string | null {
    if (workflow.scope === "entity" && !legalEntityId.trim()) {
      return "Enter a legal entity ID above to use this.";
    }
    if (workflow.scope === "project" && !projectId) {
      return "Select a project above to use this.";
    }
    return null;
  }

  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Workflows</h2>
          <p className="muted">Operations for the modules that expose no read endpoints.</p>
        </div>
      </header>

      <p className="banner banner-info">
        These modules — change control, compliance, construction and quality, customer lifecycle,
        finance and project controls — publish writes but no reads. Atlas exposes 104 POST
        endpoints against 11 GET, and none of the GETs belong here, so there is nothing to build a
        register or a detail page from. Actions on an existing record ask for its ID because the
        API offers no way to list one.
      </p>

      <ScopeBar requireProject />

      <div className="tabs tabs-wrap" role="tablist">
        {CATALOG.map((entry, index) => (
          <button
            key={entry.phase}
            role="tab"
            aria-selected={index === groupIndex}
            className={index === groupIndex ? "tab tab-active" : "tab"}
            onClick={() => setGroupIndex(index)}
          >
            {entry.phase} · {entry.title}
          </button>
        ))}
      </div>

      {group && (
        <>
          <p className="muted">{group.blurb}</p>
          <div className="stack">
            {group.workflows.map((workflow) => (
              <ActionForm
                key={workflow.key}
                title={workflow.title}
                {...(workflow.description ? { description: workflow.description } : {})}
                path={(values) =>
                  workflow.path(
                    { entity: encodeURIComponent(legalEntityId.trim()), project: encodeURIComponent(projectId) },
                    values,
                  )
                }
                fields={workflow.fields}
                {...(workflow.pathFields ? { pathFields: workflow.pathFields } : {})}
                submitLabel={workflow.submitLabel}
                disabledReason={blockedReason(workflow)}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
