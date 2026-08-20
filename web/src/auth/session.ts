// Where the opaque session token lives in the browser.
//
// The backend issues an opaque, server-revocable token — never a JWT — and
// expects it in an Authorization: Bearer header, so the client has to hold it
// somewhere reachable from JavaScript. sessionStorage is used rather than
// localStorage because it is scoped to the tab and cleared when the tab
// closes, which limits how long a token survives on a shared workstation.
//
// This is NOT the strongest available option. An httpOnly, Secure, SameSite
// cookie would keep the token out of reach of any injected script, but that
// needs the backend to set and read a cookie rather than return the token in
// a JSON body. Until then a successful XSS can read this token, and the
// mitigation is that tokens are short-lived and revocable server-side.
// Recorded for owner review in docs/production-readiness-todo.md.

const TOKEN_KEY = "atlas.session.token";
const EXPIRY_KEY = "atlas.session.expires_at";

export interface StoredSession {
  token: string;
  expiresAt: string;
}

export function storeSession(session: StoredSession): void {
  sessionStorage.setItem(TOKEN_KEY, session.token);
  sessionStorage.setItem(EXPIRY_KEY, session.expiresAt);
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EXPIRY_KEY);
}

export function readSession(): StoredSession | null {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const expiresAt = sessionStorage.getItem(EXPIRY_KEY);
  if (token === null || expiresAt === null) return null;
  // A locally-expired token is discarded rather than sent. The server is still
  // the authority — this only avoids a pointless round trip and a 401 flash.
  if (Number.isFinite(Date.parse(expiresAt)) && Date.parse(expiresAt) <= Date.now()) {
    clearSession();
    return null;
  }
  return { token, expiresAt };
}
