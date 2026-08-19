import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const NAV: { to: string; label: string }[] = [
  { to: "/dashboard", label: "Dashboards" },
  { to: "/projects", label: "Projects" },
  { to: "/documents", label: "Documents" },
  { to: "/land", label: "Land" },
  { to: "/commercial", label: "Commercial" },
  { to: "/workflows", label: "Workflows" },
  { to: "/assistant", label: "Assistant" },
  { to: "/owner-console", label: "Owner console" },
];

export function Layout() {
  const { session, signOut } = useAuth();

  const expires = session ? new Date(session.expiresAt) : null;
  const expiryLabel =
    expires && Number.isFinite(expires.getTime())
      ? expires.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="auth-mark" aria-hidden="true" />
          <strong>Atlas</strong>
        </div>
        <nav className="topbar-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "nav-active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-session">
          {expiryLabel && <span className="muted small">Session until {expiryLabel}</span>}
          <button className="btn btn-small" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
