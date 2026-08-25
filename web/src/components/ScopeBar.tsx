import { useScope } from "../context/ScopeContext";

// The legal entity and project every screen works within.
//
// The entity is typed rather than picked: no endpoint lists legal entities, so
// there is nothing to populate a dropdown from. Projects can be listed within
// an entity, so those do become a dropdown.

export function ScopeBar({ requireProject = false }: { requireProject?: boolean }) {
  const {
    legalEntityId,
    projectId,
    projects,
    projectsError,
    loadingProjects,
    setLegalEntityId,
    setProjectId,
  } = useScope();

  return (
    <div className="scope-bar">
      <label className="field field-inline">
        <span>Legal entity ID</span>
        <input
          defaultValue={legalEntityId}
          placeholder="00000000-0000-0000-0000-000000000000"
          spellCheck={false}
          autoComplete="off"
          onBlur={(event) => {
            if (event.target.value.trim() !== legalEntityId) {
              setLegalEntityId(event.target.value.trim());
            }
          }}
        />
      </label>

      {requireProject && (
        <label className="field field-inline">
          <span>Project</span>
          <select
            value={projectId}
            disabled={projects.length === 0}
            onChange={(event) => setProjectId(event.target.value)}
          >
            <option value="">
              {loadingProjects
                ? "Loading…"
                : projects.length === 0
                  ? "No projects in scope"
                  : "Select a project"}
            </option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name} ({project.code})
              </option>
            ))}
          </select>
        </label>
      )}

      {projectsError && <span className="scope-error">{projectsError}</span>}
    </div>
  );
}

/** The message a screen shows when it cannot act until the scope is set. */
export function scopeGuard(
  legalEntityId: string,
  projectId: string,
  needsProject: boolean,
): string | null {
  if (!legalEntityId.trim()) return "Enter a legal entity ID above to continue.";
  if (needsProject && !projectId) return "Select a project above to continue.";
  return null;
}
