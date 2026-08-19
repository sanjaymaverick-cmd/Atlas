import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { LoginScreen } from "./screens/LoginScreen";
import { OwnerConsoleScreen } from "./screens/OwnerConsoleScreen";
import { ProjectsScreen } from "./screens/ProjectsScreen";

export function App() {
  const { session } = useAuth();

  // No session, no shell. Every route below the layout assumes a bearer token
  // exists; the API client throws immediately if it does not.
  if (session === null) return <LoginScreen />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/projects" element={<ProjectsScreen />} />
        <Route path="/owner-console" element={<OwnerConsoleScreen />} />
        <Route path="*" element={<Navigate to="/projects" replace />} />
      </Route>
    </Routes>
  );
}
