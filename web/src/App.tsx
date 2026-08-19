import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { ScopeProvider } from "./context/ScopeContext";
import { AssistantScreen } from "./screens/AssistantScreen";
import { CommercialScreen } from "./screens/CommercialScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { DocumentsScreen } from "./screens/DocumentsScreen";
import { LandScreen } from "./screens/LandScreen";
import { LoginScreen } from "./screens/LoginScreen";
import { OwnerConsoleScreen } from "./screens/OwnerConsoleScreen";
import { ProjectsScreen } from "./screens/ProjectsScreen";
import { WorkflowsScreen } from "./screens/WorkflowsScreen";

export function App() {
  const { session } = useAuth();

  // No session, no shell. Every route below the layout assumes a bearer token
  // exists; the API client throws immediately if it does not.
  if (session === null) return <LoginScreen />;

  return (
    <ScopeProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<DashboardScreen />} />
          <Route path="/projects" element={<ProjectsScreen />} />
          <Route path="/documents" element={<DocumentsScreen />} />
          <Route path="/land" element={<LandScreen />} />
          <Route path="/commercial" element={<CommercialScreen />} />
          <Route path="/workflows" element={<WorkflowsScreen />} />
          <Route path="/assistant" element={<AssistantScreen />} />
          <Route path="/owner-console" element={<OwnerConsoleScreen />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </ScopeProvider>
  );
}
