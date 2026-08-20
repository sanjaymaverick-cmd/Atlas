// The single place the browser talks to Atlas.
//
// Deliberately hand-written and dependency-free. The usual SPA auth libraries
// model bearer tokens they can refresh or decode; Atlas issues an opaque,
// server-revocable token with no client-readable claims, and enrollment
// requires an owner to approve the device out of band. There is nothing for a
// library to do here except get in the way.

import { readSession, clearSession } from "../auth/session";
import type { ApiErrorBody } from "./types";

/** A failure the server described in its shared error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when re-authenticating could plausibly help. */
  get isAuthFailure(): boolean {
    return this.status === 401;
  }

  /** The backend asks for a fresh passkey verification, not a new session. */
  get needsStepUp(): boolean {
    return this.code === "step_up_required";
  }
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

interface RequestOptions {
  method?: Method;
  body?: unknown;
  /** Endpoints such as the WebAuthn ceremonies are reached without a session. */
  anonymous?: boolean;
}

let onAuthLost: (() => void) | null = null;

/** Let the app react once when a stored session turns out to be dead. */
export function setAuthLostHandler(handler: (() => void) | null): void {
  onAuthLost = handler;
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "unknown";
  let message = `request failed with status ${response.status}`;
  let details: unknown;
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    // A non-JSON body (a proxy error page, say) leaves the defaults in place.
  }
  return new ApiError(response.status, code, message, details);
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, anonymous = false } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (!anonymous) {
    const session = readSession();
    if (session === null) {
      throw new ApiError(401, "unauthenticated", "no active session");
    }
    headers["Authorization"] = `Bearer ${session.token}`;
  }

  // Built up rather than declared inline: under exactOptionalPropertyTypes an
  // explicit `body: undefined` is not the same as omitting it.
  const init: RequestInit = {
    method,
    headers,
    // The token travels in a header, so no cookies are wanted or sent.
    credentials: "omit",
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  const response = await fetch(path, init);

  if (!response.ok) {
    const error = await parseError(response);
    // A 401 against a session we believed in means the server revoked or
    // expired it. Drop it rather than retrying with a token known to be dead.
    if (error.isAuthFailure && !anonymous) {
      clearSession();
      onAuthLost?.();
    }
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
