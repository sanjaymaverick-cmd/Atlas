# Atlas — Private Real Estate Development ERP

Private, self-hosted operating platform for a multi-entity real estate
development group. See `docs/ERP_Technical_Blueprint_v2.docx` for the full
architecture and `db/schema.sql` for the PostgreSQL schema.

## Status

**Phases 1-10 built locally; Phase 11 is a fail-closed AI safety boundary with
no inference provider wired up.** Work is on the `phase-1-foundation` branch
(draft PR #1); `main` is still at the Phase 0 commit.

**Start here:** `docs/phase-11-resume-handoff.md` is the authoritative handover —
current state, environment setup, verified gates, known-broken items, and the
ordered list of what to do next. `docs/production-readiness-todo.md` is the
register of every decision the owner must sign off before go-live.

As of 2026-08-18 the 38 PostgreSQL integration tests pass for the first time.
They had never executed: `db/schema.sql` could not be applied to an empty
database, and because the suite skips when `ATLAS_TEST_DATABASE_URL` is unset,
that failed silently from Phase 3 onward. Phases 1-10 were therefore signed off
without their database-backed behaviour ever being exercised. Full suite is now
316 passed. `alembic upgrade head` now provisions a database from empty too —
verified against a real, from-empty PostgreSQL 16 container using the
documented `asyncpg` URL; see `docs/phase-11-resume-handoff.md` defect C for
what was actually broken (three separate issues, not one). One gate remains
red and is documented, not hidden: strict mypy has 6 unresolved errors from a
deprecated PyMuPDF import.

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
2. **Passkey device binding** with persistent, one-time WebAuthn registration
   and authentication ceremonies, owner-approved enrollment, and
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

Phase 2 now adds project-scoped document/drawing records, immutable binary
revisions, append-only local object storage with SHA-256 verification, malware
scan quarantine state, linear review/approval/issue transitions, session-bound
watermarked PDF previews, and four-eyes export approval with one-time downloads.

Phase 3 adds scoped land parcels, due-diligence findings and evidence links,
legal approval lifecycles, loan/EMI/PDC obligations, RERA registrations, and
statutory obligations. Lifecycle mutations are versioned and audited in the
same transaction; invalid state jumps are rejected as conflicts.

Phase 4 adds budgets and lines, gated vendor onboarding and KYC evidence,
purchase orders, contracts and milestones, insurance, and labour-compliance
records. Purchase orders cannot be issued until the vendor is active, and
executed contracts require immutable document evidence.

Plus the §15 nine-dimension access check, the secrets/KMS pluggability boundary
for the undecided §25 item 2, module boundaries enforced by import-linter, and
a CI pipeline covering lint, types, boundaries, tests, coverage and security.

The test suite includes database-free service and HTTP contract tests plus
PostgreSQL integration coverage for schema, audit, authentication, projects,
and document revision transactions. Without `ATLAS_TEST_DATABASE_URL`, the
PostgreSQL-dependent integration tests are reported as skipped rather than
passed; CI always runs them against PostgreSQL 16.

### Next

Complete Phase 4 verification, then begin Phase 5 locally. Real WebAuthn UAT,
encrypted production object storage, malware-scanner selection, staging, and DR
provisioning remain pre-launch gates tracked in
`docs/production-readiness-todo.md`.

## Repository layout

```
atlas/
  api/            FastAPI factory, dependencies, and thin HTTP adapters
  platform/       cross-cutting: db, secrets, kms, audit chain, access control
  modules/        identity, organization, documents, land, compliance, commercial, audit
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
database URL and the WebAuthn relying-party configuration:

```bash
export ATLAS_DATABASE_URL='postgresql+asyncpg://atlas:development-only@localhost/atlas'
export ATLAS_WEBAUTHN_RP_ID='localhost'
export ATLAS_WEBAUTHN_RP_NAME='Atlas Local'
export ATLAS_WEBAUTHN_ORIGIN='http://localhost:8000'
export ATLAS_DOCUMENT_STORAGE_ROOT="$PWD/.atlas-data/documents"
alembic upgrade head
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

WebAuthn registration and authentication are under
`/api/v1/auth/webauthn`. Registration creates a `pending_approval` device; it
cannot authenticate until the existing owner-console approval flow activates
it. Authentication returns an opaque, revocable session token—never a JWT.
Challenges are database-backed, expire after five minutes, and are consumed on
the first verification attempt.

Production and staging WebAuthn origins must be exact HTTPS origins, and the RP
ID must be their registrable domain. `localhost` HTTP is only for local
development.

Document operations are under `/api/v1/projects/{project_id}/documents` and
`/api/v1/documents/{document_id}`. Binary revision intake generates the object
key on the server. Cleared revisions may receive short-lived, session-bound PDF
preview grants; preview responses are watermarked, metadata-scrubbed,
non-cacheable, and sandboxed. Original-file exports require a fresh passkey
step-up, approval by someone other than the requester, and are single-use.

Phase 3 operations are exposed under `/api/v1/land-parcels`, `/api/v1/loans`,
`/api/v1/rera-registrations`, and `/api/v1/compliance-obligations`, with creation
paths rooted in their legal-entity or project scope. Reference numbers are
operational metadata only; do not place account numbers, cheque images,
credentials, or payment secrets in these fields.

Phase 4 operations are under `/api/v1/budgets`, `/api/v1/purchase-orders`,
`/api/v1/contracts`, and the vendor onboarding routes. KYC evidence must point
to a restricted Documents record. Do not put account numbers, cheque images,
signatures, credentials, or raw evidence into reference fields or API logs.

Phase 5 operations cover schedule activities and progress, offline-idempotent
site diaries, EHS incidents, inspection templates and executions, document-backed
evidence, and snag lifecycles under `/api/v1`. Visitor information is accepted as
a count only; safety narratives and checklist content are excluded from audit
payloads. PostgreSQL integration tests require `ATLAS_TEST_DATABASE_URL` and are
reported as skipped—not passed—when it is absent.

Phase 6 operations cover document-backed BIM imports, project CostCode WBS,
quantity verification/approval, material masters, receipts, and receipt-linked
issuances under `/api/v1`. BIM callers provide a restricted Documents UUID—not
a path or URL. Material issuance is serialized against its receipt and rejects
cumulative quantities above accepted stock. Formal discrepancy/change handling
remains in Phase 7.

Phase 7 operations cover change requests, RFIs, NCRs, and quantity discrepancy
cases under `/api/v1`. The workflows enforce ordered transitions, controlled
Documents evidence, decision attribution, routed-recipient responses, and
reinspection before NCR closure. Confidential narrative fields are not copied
into audit payloads or notification infrastructure.

Phase 8 operations cover bookings, payment plans/installments, collections and
allocation, registration, possession, and executed customer-contract linkage
under `/api/v1`. The service prevents cross-project unit booking, more than one
active booking per unit, installment/collection over-allocation, and linkage to
an unexecuted or wrong-customer contract. APIs accept controlled Documents IDs,
not embedded PII, bank credentials, signatures, or provider payloads.

Phase 9 operations cover controlled Tally export registration, validation,
normalized voucher ingestion, discrepancy cases, and accountant review under
`/api/v1`. Tally remains the statutory book of record: Atlas cannot post or
amend vouchers. Source exports stay in restricted Documents records; APIs and
audit events retain only controlled document IDs, SHA-256 provenance, normalized
facts, and redacted indicators for ledger, voucher, and resolution narratives.

Phase 10 operations expose project/legal-entity CEO dashboards and queued,
audited PDF/XLSX report requests under `/api/v1`. Production startup requires a
distinct `ATLAS_REPORTING_DATABASE_URL`; aggregate reads use that read-replica
session and never reuse the transactional session. Responses contain aggregate
metrics and opaque IDs only. Report generation remains queued for a controlled
worker and never sends or publishes an export from the HTTP request.

Phase 11 safety foundations expose a fail-closed assistant evaluation endpoint
under `/api/v1/assistant`. The default provider is disabled because the
Blueprint §25 hosting decision still requires owner sign-off. Authority policy,
prompt-injection refusal, confidence gating, minimized digest-only persistence,
and adversarial tests are implemented without selecting a model, endpoint, or
vendor and without accepting provider keys or raw document text over HTTP.

The local filesystem adapter is for synthetic development content only. Review
every item in `docs/production-readiness-todo.md` before introducing real data.

Run the database-free HTTP tests with:

```bash
.venv/bin/python -m pytest atlas/api/tests
```

Run locally with separate transactional and reporting PostgreSQL databases:

```bash
export ATLAS_DATABASE_URL='postgresql+asyncpg://localhost/atlas'
export ATLAS_REPORTING_DATABASE_URL='postgresql+asyncpg://localhost/atlas_reporting'
```

## Confidentiality

Strictly confidential. Do not make this repository public.
