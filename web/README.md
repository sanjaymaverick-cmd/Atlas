# Atlas web client

React + Vite + TypeScript. The first vertical slice: passkey sign-in, opaque
session handling, projects, and an honest account of what the owner console
does and does not expose over HTTP.

Strictly confidential, like the rest of the repository. Not for publication.

## Running it

The API must be running first, and it must be told that this dev server is the
WebAuthn origin — see the gotcha below.

```bash
export ATLAS_DATABASE_URL='postgresql+asyncpg://atlas@/atlas?host=/tmp&port=55432'
export ATLAS_REPORTING_DATABASE_URL='postgresql+asyncpg://atlas@/atlas_reporting?host=/tmp&port=55432'
export ATLAS_WEBAUTHN_RP_ID='localhost'
export ATLAS_WEBAUTHN_ORIGIN='http://localhost:5173'
export ATLAS_DOCUMENT_STORAGE_ROOT="$PWD/.atlas-data/documents"
uvicorn atlas.api.application:create_default_app --factory --port 8000
```

Then:

```bash
npm install
npm run dev
```

`npm run typecheck` runs TypeScript alone; `npm run build` typechecks and then
builds.

## Two things that will otherwise waste your afternoon

**1. `ATLAS_WEBAUTHN_ORIGIN` must be the dev server's origin, not the API's.**
The Vite dev server proxies `/api` and `/health` to port 8000 so the browser
only ever sees one origin. The browser stamps *its own* origin into the
WebAuthn `clientDataJSON`, and the backend compares that against
`ATLAS_WEBAUTHN_ORIGIN` exactly. During development that value is
`http://localhost:5173`. `ATLAS_WEBAUTHN_RP_ID` stays `localhost`, because an
RP ID is a domain and ignores the port. In production both point at the real
HTTPS origin and this distinction disappears.

**2. The first sign-in cannot be done from the browser alone.** Enrolling a
passkey creates a device with status `pending_approval`, and it cannot
authenticate until an owner approves it. There is no HTTP route for that
approval — it is a CLI operation, deliberately (Blueprint §15). So the
bootstrap is:

```bash
python -m atlas.owner_console.cli devices pending
python -m atlas.owner_console.cli devices approve <device-id> --owner-id <owner-uuid>
```

The **Owner console** page in the app documents these commands rather than
performing them, which is the honest thing for it to do: exposing owner
operations over HTTP is a security decision for the repository owner, not
something a frontend should introduce quietly.

## Shape of the code

```
src/
  api/client.ts     the only place that talks to Atlas; bearer token, error envelope
  api/types.ts      hand-written mirrors of atlas/api/schemas.py
  auth/session.ts   where the opaque token lives, and why
  auth/passkey.ts   WebAuthn ceremonies and the base64url conversions they need
  auth/AuthContext  session state for the app
  screens/          one file per screen
  components/       the signed-in shell
```

Deliberately dependency-light. The API client is hand-written because the usual
SPA auth libraries model tokens they can decode or refresh, and Atlas issues an
opaque, server-revocable token with no client-readable claims and an
out-of-band device-approval step. There is nothing for such a library to do.

## Known limitations

- **Passkey login is unverified end to end.** The ceremony code is written
  against the backend's actual wire format, but completing one needs a platform
  authenticator gesture that cannot be automated, so it has not been exercised
  against a real authenticator. Reads and writes were verified with a seeded
  session instead. Treat first real login as untested.
- **Token storage is `sessionStorage`**, which any injected script can read. An
  httpOnly cookie would be stronger but needs a backend change. Recorded for
  owner review in `docs/production-readiness-todo.md`.
- **Scope is Phase 1 only.** Projects and authentication. The other ~90
  endpoints — documents, land, commercial, construction, customer lifecycle,
  finance, reporting, AI — have no UI yet.
- **No tests.** The API client and the base64url conversions in `passkey.ts` are
  the two pieces most worth covering, and neither is covered.
