# Atlas — Private Real Estate Development ERP

Private, self-hosted operating platform for a multi-entity real estate
development group. See `docs/ERP_Technical_Blueprint_v2.docx` for the full
architecture and `db/schema.sql` for the PostgreSQL schema.

## Status

**Phase 1 in progress** — foundation layer built and tested.

Phase 0.5's spike decisions are recorded in `docs/phase-0.5-decision-memo.md`:
the event and reporting-store choices adopt the blueprint's stated defaults;
AI hosting remains open and gates Phase 11 only. None of the six Blueprint §25
owner decisions block Phase 1 — see the memo for how each is kept swappable.

Two of those decisions are worth starting now regardless, because their lead
time is not code: **who holds the break-glass credential** (§25 item 4 — they
need briefing and a physically sealed reference) and **the warm-standby
location** (§25 item 6 — the quarterly restore drill cannot start until the
site exists).

### Built

All seven Phase 1 items from `CLAUDE_CODE_KICKOFF.md`:

1. **Schema applied** to PostgreSQL 16 via an Alembic baseline. Two critical
   audit-chain defects found and fixed — see `docs/schema-findings-phase1.md`
2. **Passkey device binding** with owner-approved enrollment and WebAuthn
   signature-counter clone detection
3. **Short-lived sessions** (opaque server-revocable tokens) with step-up
   authentication that expires
4. **Legal entity and project CRUD**, scoped by `identity.user_roles`
5. **Audit pipeline** — every mutation writes a hash-chained event in the same
   transaction, with an independent verifier that walks and recomputes the chain
6. **Owner console** with the break-glass secondary-admin flow, fully audited
7. **Backup observability** — WAL archiving and object-storage sync assessed
   against the §3.2 RPO targets
8. **FastAPI HTTP layer** — opaque bearer-session authentication, safe
   health/readiness checks, and scoped project operations over the existing
   services

Plus the §15 nine-dimension access check, the secrets/KMS pluggability boundary
for the undecided §25 item 2, module boundaries enforced by import-linter, and
a CI pipeline covering lint, types, boundaries, tests, coverage and security.

The test suite includes database-free service and HTTP contract tests plus
PostgreSQL integration coverage for schema, audit, authentication, and project
transactions. The current suite collects 207 tests; without
`ATLAS_TEST_DATABASE_URL`, 171 pass and 36 PostgreSQL-dependent integration
tests are reported as skipped rather than passed.

### Next

Phase 1 remaining: the WebAuthn ceremony against a real authenticator and the
DR/warm-standby infrastructure work (tracked, gated on §25 items 3 and 6).

## Repository layout

```
atlas/
  api/            FastAPI factory, dependencies, and thin HTTP adapters
  platform/       cross-cutting: db, secrets, kms, audit chain, access control
  modules/        identity, organization, audit
  owner_console/  admin API + CLI
db/schema.sql     canonical PostgreSQL DDL, all domains
docs/             blueprint, audit report, decision memo, module boundaries
tests/            integration tests (require a live PostgreSQL)
```

## Getting started

```bash
make install                       # venv + dependencies
make test-unit                     # no database needed
make check                         # everything CI runs
```

Integration tests need PostgreSQL 14+ and `ATLAS_TEST_DATABASE_URL`. See
`docs/local-postgres.md`, which includes a rootless setup for machines with
neither Docker nor sudo.

## HTTP API

The production entry point is the application factory
`atlas.api.application:create_default_app`. It requires an async SQLAlchemy
database URL in `ATLAS_DATABASE_URL`:

```bash
export ATLAS_DATABASE_URL='postgresql+asyncpg://atlas:development-only@localhost/atlas'
uvicorn atlas.api.application:create_default_app --factory --reload
```

The example credential is synthetic and local-only. Keep real database
credentials in the configured secrets provider, not in source or shell history.

Liveness is available at `GET /health/live`; readiness at
`GET /health/ready` verifies database connectivity without returning a URL or
credentials. Project operations are under `/api/v1` and require the existing
opaque session token:

```http
Authorization: Bearer <opaque-session-token>
```

Run the database-free HTTP tests with:

```bash
.venv/bin/python -m pytest atlas/api/tests
```

## Confidentiality

Strictly confidential. Do not make this repository public.
