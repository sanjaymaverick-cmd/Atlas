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
  signOut: () => void;
}

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

  const signOut = useCallback(() => {
    // Local only. The opaque token stays valid server-side until it expires or
    // is revoked; there is no logout endpoint to call.
    clearSession();
    setSession(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
