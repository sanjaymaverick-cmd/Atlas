import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { request } from "../api/client";
import type { Project } from "../api/types";

// Almost every Atlas endpoint is rooted in a legal entity or a project, because
// authorisation is scoped that way (Blueprint §2, §15). Rather than make every
// screen ask for the same two UUIDs, the scope is chosen once and shared.
//
// The legal entity is typed in: there is no endpoint that lists legal entities,
// so the UI cannot offer a picker for it. Projects can be listed within an
// entity, so those become a dropdown once an entity is set.

const ENTITY_KEY = "atlas.scope.legal_entity_id";
const PROJECT_KEY = "atlas.scope.project_id";

interface ScopeState {
  legalEntityId: string;
  projectId: string;
  projects: Project[];
  projectsError: string | null;
  loadingProjects: boolean;
  setLegalEntityId: (id: string) => void;
  setProjectId: (id: string) => void;
  refreshProjects: () => Promise<void>;
  /** The currently selected project, when one is chosen and known. */
  project: Project | undefined;
}

const ScopeContext = createContext<ScopeState | null>(null);

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [legalEntityId, setEntity] = useState(() => localStorage.getItem(ENTITY_KEY) ?? "");
  const [projectId, setProject] = useState(() => localStorage.getItem(PROJECT_KEY) ?? "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(false);

  const refreshProjects = useCallback(async () => {
    if (!legalEntityId.trim()) {
      setProjects([]);
      return;
    }
    setLoadingProjects(true);
    setProjectsError(null);
    try {
      const found = await request<Project[]>(
        `/api/v1/legal-entities/${encodeURIComponent(legalEntityId.trim())}/projects`,
      );
      setProjects(found);
    } catch (caught) {
      setProjects([]);
      setProjectsError(caught instanceof Error ? caught.message : "Could not load projects.");
    } finally {
      setLoadingProjects(false);
    }
  }, [legalEntityId]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  const setLegalEntityId = useCallback((id: string) => {
    localStorage.setItem(ENTITY_KEY, id);
    setEntity(id);
    // A project belongs to exactly one entity, so changing the entity
    // invalidates the selection rather than silently keeping a foreign id.
    localStorage.removeItem(PROJECT_KEY);
    setProject("");
  }, []);

  const setProjectId = useCallback((id: string) => {
    localStorage.setItem(PROJECT_KEY, id);
    setProject(id);
  }, []);

  const value = useMemo<ScopeState>(
    () => ({
      legalEntityId,
      projectId,
      projects,
      projectsError,
      loadingProjects,
      setLegalEntityId,
      setProjectId,
      refreshProjects,
      project: projects.find((candidate) => candidate.id === projectId),
    }),
    [
      legalEntityId,
      projectId,
      projects,
      projectsError,
      loadingProjects,
      setLegalEntityId,
      setProjectId,
      refreshProjects,
    ],
  );

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): ScopeState {
  const value = useContext(ScopeContext);
  if (value === null) throw new Error("useScope must be used inside ScopeProvider");
  return value;
}
