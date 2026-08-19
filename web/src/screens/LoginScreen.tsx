import { useState } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { CeremonyAbortedError, passkeysSupported, registerPasskey } from "../auth/passkey";

type Mode = "sign-in" | "enrol";

function describe(error: unknown): string {
  if (error instanceof CeremonyAbortedError) return error.message;
  if (error instanceof ApiError) {
    // The backend deliberately returns the same opaque failure for a bad
    // assertion, an unknown credential and a detected clone, so there is
    // nothing more specific to show and guessing would be misleading.
    if (error.status === 401) {
      return "That passkey could not sign in. If this device was only just enrolled, it still needs owner approval.";
    }
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

export function LoginScreen() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [deviceName, setDeviceName] = useState("");

  const supported = passkeysSupported();

  async function handleSignIn() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await signIn();
    } catch (caught) {
      setError(describe(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrol(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await registerPasskey(userId.trim(), deviceName.trim() || null);
      setNotice(
        "Passkey enrolled. This device is pending approval and cannot sign in until an owner approves it from the owner-console CLI.",
      );
    } catch (caught) {
      setError(describe(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <main className="auth-card">
        <div className="auth-brand">
          <span className="auth-mark" aria-hidden="true" />
          <div>
            <h1>Atlas</h1>
            <p className="auth-sub">Private real estate development ERP</p>
          </div>
        </div>

        {!supported && (
          <p className="banner banner-error">
            This browser cannot use passkeys. Atlas has no password sign-in by design.
          </p>
        )}

        <div className="tabs" role="tablist">
          <button
            role="tab"
            aria-selected={mode === "sign-in"}
            className={mode === "sign-in" ? "tab tab-active" : "tab"}
            onClick={() => {
              setMode("sign-in");
              setError(null);
              setNotice(null);
            }}
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={mode === "enrol"}
            className={mode === "enrol" ? "tab tab-active" : "tab"}
            onClick={() => {
              setMode("enrol");
              setError(null);
              setNotice(null);
            }}
          >
            Enrol a device
          </button>
        </div>

        {error && <p className="banner banner-error">{error}</p>}
        {notice && <p className="banner banner-ok">{notice}</p>}

        {mode === "sign-in" ? (
          <>
            <p className="muted">
              Atlas authenticates with a registered passkey. There is no password to enter.
            </p>
            <button
              className="btn btn-primary btn-block"
              onClick={handleSignIn}
              disabled={busy || !supported}
            >
              {busy ? "Waiting for your passkey…" : "Sign in with a passkey"}
            </button>
          </>
        ) : (
          <form onSubmit={handleEnrol} className="stack">
            <p className="muted">
              Enrolment binds a passkey to an existing Atlas user. An owner must then approve
              the device before it can sign in.
            </p>
            <label className="field">
              <span>User ID</span>
              <input
                required
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>
                Device name <em>optional</em>
              </span>
              <input
                value={deviceName}
                onChange={(event) => setDeviceName(event.target.value)}
                placeholder="Site laptop"
                maxLength={200}
                autoComplete="off"
              />
            </label>
            <button className="btn btn-primary btn-block" disabled={busy || !supported}>
              {busy ? "Waiting for your passkey…" : "Enrol this device"}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
