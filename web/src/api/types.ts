// Mirrors atlas/api/schemas.py. Hand-written rather than generated from the
// OpenAPI document so the client stays small and reviewable; if this drifts,
// the backend is the source of truth.

export interface Project {
  id: string;
  legal_entity_id: string;
  name: string;
  code: string;
  city: string | null;
  status: string;
  start_date: string | null;
  target_completion_date: string | null;
  version: number;
  archived_at: string | null;
}

export interface ProjectCreate {
  name: string;
  code: string;
  city?: string | null;
  status?: string;
  start_date?: string | null;
  target_completion_date?: string | null;
}

/** The `{"error": {...}}` envelope every failure shares. See atlas/api/errors.py. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface SessionGrant {
  session_token: string;
  token_type: string;
  expires_at: string;
}

export interface CeremonyOptions {
  ceremony_id: string;
  public_key: Record<string, unknown>;
}
