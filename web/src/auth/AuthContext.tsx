import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { setAuthLostHandler } from "../api/client";
import { authenticatePasskey } from "./passkey";
import { clearSession, readSession, storeSession, type StoredSession } from "./session";

interface AuthState {
  session: StoredSession | null;
  signIn: () => Promise<void>;
  /** Adopt a token minted out of band by scripts/dev_seed.py. */
  useDevelopmentToken: (token: string) => void;
  signOut: () => void;
}

// A development token has no expiry we can read — it is opaque, by design, with
// no client-readable claims. We record a nominal one so the shell can show
// something; the server remains the authority and a 401 clears the session
// whatever this says.
const DEV_TOKEN_NOMINAL_HOURS = 8;

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(() => readSession());

  // The client drops a token the server has rejected; mirror that in the UI so
  // a revoked session cannot leave a stale signed-in shell on screen.
  useEffect(() => {
    setAuthLostHandler(() => setSession(null));
    return () => setAuthLostHandler(null);
  }, []);

  const signIn = useCallback(async () => {
    const grant = await authenticatePasskey();
    const stored: StoredSession = { token: grant.session_token, expiresAt: grant.expires_at };
    storeSession(stored);
    setSession(stored);
  }, []);

  const useDevelopmentToken = useCallback((token: string) => {
    const stored: StoredSession = {
      token: token.trim(),
      expiresAt: new Date(Date.now() + DEV_TOKEN_NOMINAL_HOURS * 3_600_000).toISOString(),
    };
    storeSession(stored);
    setSession(stored);
  }, []);

  const signOut = useCallback(() => {
    // Local only. The opaque token stays valid server-side until it expires or
    // is revoked; there is no logout endpoint to call.
    clearSession();
    setSession(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ session, signIn, useDevelopmentToken, signOut }),
    [session, signIn, useDevelopmentToken, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
