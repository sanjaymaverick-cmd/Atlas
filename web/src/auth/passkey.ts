// WebAuthn ceremonies against the Atlas identity endpoints.
//
// The backend serialises its options with py_webauthn's options_to_json, which
// base64url-encodes every binary field (challenge, user.id, credential ids).
// The browser API wants ArrayBuffers, and wants them handed back base64url
// encoded again — so the conversions below are the whole job. They are
// hand-written rather than pulled from a library because getting them wrong is
// obvious immediately and the surface is small.
//
// Both ceremonies require user verification and a resident (discoverable)
// credential, so authentication needs no username: the authenticator offers
// the passkeys it holds for this relying party.

import { request } from "../api/client";
import type { CeremonyOptions, SessionGrant } from "../api/types";

// The return type is inferred rather than annotated as plain `Uint8Array`.
// Current lib.dom types make Uint8Array generic over its buffer, and only
// Uint8Array<ArrayBuffer> satisfies BufferSource — a bare `Uint8Array`
// annotation widens to ArrayBufferLike and stops type-checking against the
// WebAuthn APIs. Allocating the ArrayBuffer explicitly keeps that narrow.
function base64urlToBytes(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded.padEnd(Math.ceil(padded.length / 4) * 4, "="));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** True when this browser can run a passkey ceremony at all. */
export function passkeysSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.PublicKeyCredential === "function" &&
    typeof navigator.credentials?.create === "function"
  );
}

interface DescriptorJSON {
  id: string;
  type: string;
  transports?: string[];
}

function toDescriptors(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list) || list.length === 0) return undefined;
  return (list as DescriptorJSON[]).map((item) => ({
    id: base64urlToBytes(item.id),
    type: "public-key" as const,
    ...(item.transports
      ? { transports: item.transports as AuthenticatorTransport[] }
      : {}),
  }));
}

function encodeAssertion(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAssertionResponse &
    AuthenticatorAttestationResponse;
  const encoded: Record<string, unknown> = {
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
  };
  const inner: Record<string, unknown> = {
    clientDataJSON: bytesToBase64url(response.clientDataJSON),
  };
  if (response.attestationObject) {
    inner["attestationObject"] = bytesToBase64url(response.attestationObject);
  }
  if (response.authenticatorData) {
    inner["authenticatorData"] = bytesToBase64url(response.authenticatorData);
  }
  if (response.signature) inner["signature"] = bytesToBase64url(response.signature);
  if (response.userHandle) inner["userHandle"] = bytesToBase64url(response.userHandle);
  encoded["response"] = inner;
  return encoded;
}

/** Thrown when the browser or the person aborts the ceremony. */
export class CeremonyAbortedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CeremonyAbortedError";
  }
}

async function runCeremony(
  options: CeremonyOptions,
  kind: "create" | "get",
): Promise<Record<string, unknown>> {
  const publicKey = options.public_key as Record<string, unknown>;
  const challenge = base64urlToBytes(publicKey["challenge"] as string);

  let credential: Credential | null;
  try {
    // Descriptor lists are spread in only when present: an explicit
    // `undefined` is rejected under exactOptionalPropertyTypes, and an absent
    // allowCredentials is exactly what makes usernameless sign-in work.
    if (kind === "create") {
      const user = publicKey["user"] as { id: string; name: string; displayName: string };
      const exclude = toDescriptors(publicKey["excludeCredentials"]);
      credential = await navigator.credentials.create({
        publicKey: {
          ...(publicKey as unknown as PublicKeyCredentialCreationOptions),
          challenge,
          user: { ...user, id: base64urlToBytes(user.id) },
          ...(exclude ? { excludeCredentials: exclude } : {}),
        },
      });
    } else {
      const allow = toDescriptors(publicKey["allowCredentials"]);
      credential = await navigator.credentials.get({
        publicKey: {
          ...(publicKey as unknown as PublicKeyCredentialRequestOptions),
          challenge,
          ...(allow ? { allowCredentials: allow } : {}),
        },
      });
    }
  } catch (cause) {
    // NotAllowedError covers both a cancelled prompt and a timeout, and the
    // spec deliberately does not distinguish them.
    throw new CeremonyAbortedError(
      cause instanceof Error && cause.name === "NotAllowedError"
        ? "the passkey prompt was dismissed or timed out"
        : "the passkey ceremony could not be completed",
    );
  }

  if (credential === null) throw new CeremonyAbortedError("no passkey was returned");
  return encodeAssertion(credential as PublicKeyCredential);
}

/**
 * Enrol this device for an existing user.
 *
 * The resulting device is created `pending_approval` and cannot sign in until
 * an owner approves it through the owner-console CLI. That is deliberate
 * (Blueprint §15) and there is no HTTP route to approve it.
 */
export async function registerPasskey(
  userId: string,
  deviceName: string | null,
): Promise<{ device_id: string; status: string }> {
  const options = await request<CeremonyOptions>(
    "/api/v1/auth/webauthn/registration/options",
    { method: "POST", body: { user_id: userId }, anonymous: true },
  );
  const credential = await runCeremony(options, "create");
  return request("/api/v1/auth/webauthn/registration/verify", {
    method: "POST",
    anonymous: true,
    body: {
      ceremony_id: options.ceremony_id,
      credential,
      ...(deviceName ? { device_name: deviceName } : {}),
    },
  });
}

/** Sign in with an approved passkey, returning an opaque session token. */
export async function authenticatePasskey(): Promise<SessionGrant> {
  const options = await request<CeremonyOptions>(
    "/api/v1/auth/webauthn/authentication/options",
    { method: "POST", anonymous: true },
  );
  const credential = await runCeremony(options, "get");
  return request<SessionGrant>("/api/v1/auth/webauthn/authentication/verify", {
    method: "POST",
    anonymous: true,
    body: { ceremony_id: options.ceremony_id, credential },
  });
}
