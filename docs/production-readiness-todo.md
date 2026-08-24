# Production-readiness decisions and TODOs

This register records provisional choices made while Atlas is built locally.
Every item must be reviewed, replaced where necessary, and explicitly signed
off before production data or users are introduced.

## Global security and infrastructure

- [ ] Select and configure the production secrets manager and KMS/HSM. Local
  environment-variable providers are development-only and must remain unable
  to start in production mode.
- [ ] Replace every synthetic/local database URL, relying-party origin, host,
  certificate, and object-storage endpoint with secret-managed production
  configuration. Never commit the resulting values.
- [ ] Confirm the WebAuthn RP ID and exact HTTPS origins; perform real-device
  UAT and document supported browser/authenticator combinations.
- [ ] Confirm RTO/RPO, warm-standby location, backup retention, key custodians,
  and quarterly restore-drill ownership.
- [ ] Name the break-glass credential holder and incident commander; seal and
  test the recovery procedure without recording credential material here.
- [ ] Configure WAF, rate limiting, private network access, TLS policy, security
  headers, log redaction, monitoring, alert routing, vulnerability scanning,
  dependency updates, and incident-response notification obligations.
- [ ] Review data classification, retention, legal holds, archival, privacy
  notices, data-subject procedures, and jurisdiction-specific compliance with
  qualified legal/security advisers.
- [ ] Run a production threat-model review, penetration test, access-control
  review, audit-chain verification, restore drill, and secrets scan before
  launch.
- [ ] Confirm whether the GitHub repository should remain public. It is public
  as of 2026-08-17. The tree is synthetic-data-only today, but hosting choices,
  schema detail, and the break-glass design are all visible. Decide before any
  real data, deployment configuration, or credential material is introduced.

## Verification integrity — found 2026-08-17/18

Found when the Phase 11 completion gates were rerun against a real PostgreSQL
instance. None was introduced by Phase 11; all predate it.

- [x] RESOLVED 2026-08-18: `db/schema.sql` could not be applied to a clean
  database. `land.due_diligence_items` referenced `documents.documents(id)`
  before the `documents` schema was created, so a clean apply failed with
  `relation "documents.documents" does not exist`. The `documents` section was
  relocated to sit after `organization` and before `land`. The move is a pure
  relocation — sorted file contents are identical before and after, so no
  statement changed and the resulting object set is unchanged.
  Effect: the 38 PostgreSQL integration tests now pass for the first time
  (0 skipped), and migration `0001_baseline`, which applies `db/schema.sql`
  verbatim, now succeeds against an empty database (89 tables).
- [x] RATIFIED 2026-08-18 by the repository owner: the edit to `db/schema.sql`
  in commit `b990bdc` is an approved exception to the freeze `0001_baseline`
  declares from that revision onward.

  Grounds for the exception, recorded so the decision can be audited later:
  the file as committed could not be applied by any path, which made
  `0001_baseline` itself unrunnable; the change is a pure relocation whose
  sorted contents are identical before and after, so no statement was added,
  removed, or altered; and the resulting object set is unchanged, so no
  already-provisioned database diverges from one built after the change.

  Scope of this ratification: **this specific reordering only.** It is not
  standing permission to edit `db/schema.sql`. The freeze otherwise stands, and
  any future change to the file needs its own recorded exception or a new
  Alembic revision.

- [x] DECIDED 2026-08-18 by the repository owner — the freeze rule is
  **withdrawn and replaced by a checkable invariant.** The rule had already
  been breached far more widely than the single `4e4c85d` case recorded here:
  every phase from 2 onward edited `db/schema.sql` while its Alembic revision
  claimed to add the same objects, which is why the file ended up holding the
  complete 11-phase schema and why the migration chain could not provision a
  database at all. A prose declaration in a docstring was not an enforcement
  mechanism, and enforcing it retroactively would have meant unwinding eleven
  phases of accumulated practice.

  What replaces it: `db/schema.sql` is no longer frozen. It remains the
  readable canonical description (Blueprint §6), and every schema change must
  now land in **both** places — real DDL in a new Alembic revision, and the
  matching edit to the file. `tests/integration/test_migration_schema_
  equivalence.py` provisions two databases from empty, one through
  `alembic upgrade head` and one from `db/schema.sql`, and fails if the
  resulting schemas differ. CI runs it by name, alongside the audit
  hash-chain test, so a skip cannot be mistaken for a pass.

  Verified in both directions before adoption: it passes today (the two paths
  agree across all 2,515 dumped schema lines) and it actually catches drift
  (a table injected into `0012` failed the check and was named in the diff).
  The freeze declaration in `0001_baseline`'s docstring has been rewritten to
  match. The `b990bdc` ratification above is now historical: with no freeze,
  the file no longer needs per-edit exceptions.

  Consequence to keep in view: revisions `0002`-`0012` are no-ops because the
  baseline already creates everything. That is a one-time artefact of the old
  rule's failure. The first genuine post-go-live schema change must carry real
  DDL, because `db/schema.sql` cannot be applied to a database that holds
  data — the equivalence test enforces that the DDL exists, but only a human
  can judge that it is the *right* incremental change.
- [ ] RE-VERIFY EARLIER PHASES: because integration tests had never executed,
  Phases 1-10 were each signed off without their database-backed behaviour ever
  being exercised — audit hash-chain, append-only triggers, break-glass,
  session-token auth, and same-transaction audit writes included. Those tests
  now pass, but confirm the per-phase sign-offs are re-recorded on that basis
  rather than left resting on the earlier, weaker evidence.
  - [x] Phase 3 checkpoint, 2026-08-23: a real `LandService` parcel mutation
    commits with exactly one valid hash-chain event, and rolling the service
    call back removes both business row and event. This proves transaction
    atomicity for that mutation only; Phase 3 optimistic concurrency, archival,
    compliance mutations, and the same guarantees in Phases 4-10 remain open.
- [x] RESOLVED 2026-08-18: `alembic upgrade head` failed on a clean database.
  The recorded cause (`0002_webauthn_challenges` re-creating a table
  `0001_baseline` already made via `db/schema.sql`) was real but was only the
  first of three defects. `db/schema.sql` is not a Phase-1 snapshot but the
  full end-state schema for all 11 phases, so migrations `0002`-`0012` were
  *all* redundant with the baseline and would each have collided in turn;
  additionally `alembic/env.py` built a sync engine for the documented async
  `asyncpg` URL, and `0001_baseline` executed the whole schema file as one
  multi-statement string, which asyncpg cannot do. Since Atlas has no
  previously-provisioned database anywhere, `0002`-`0012` are now documented
  no-ops, `env.py` uses Alembic's async recipe, and the baseline splits the
  file into individual statements. Verified from empty against PostgreSQL 16
  using the documented URL: 89 tables, head `0012_phase11_ai_safety`. A CI
  step now covers the path. No owner decision outstanding.
- [x] RESOLVED 2026-08-18: strict mypy. **The recorded diagnosis was wrong on
  both counts and the correction is worth reading before trusting this
  register's other type-checking claims.** The 6 `fitz` errors did not
  reproduce — strict mypy was already clean (157 files, verified with
  `--no-incremental` to rule out cache staleness) before any change. The
  original errors are best explained by this project's own note that
  `~/.atlas-venv` was missing `pymupdf` entirely: an absent package yields
  `import-not-found` plus an unused-ignore per file, 3 x 2 = the 6 reported.
  That is an incomplete virtualenv, not a code defect. Worse, the approved fix
  would have *regressed* the gate: switching to `import pymupdf` took the tree
  from 0 errors to 20, because PyMuPDF ships a `py.typed` marker without
  actually annotating its callables, so strict mode rejects every call into it.
  A `py.typed` marker asserts typedness; it does not supply it. The imports
  were still moved to `pymupdf` for deprecation-safety (the `fitz` alias warns
  at runtime and is slated for removal), paired with a
  `follow_imports = "skip"` override that preserves the clean result, and the
  dependency is pinned to `pymupdf>=1.28.2,<1.29`. Verified: mypy clean, 278
  unit and 24 documents tests pass, Ruff clean, no `fitz` import remains.
- [x] RESOLVED 2026-08-20 — **the scoped authorisation path was broken in
  every environment, and the test suite did not notice.**
  `identity/repository.load_grants` joins roles to permissions through
  `Base.metadata.tables["identity.role_permissions"]`. That table exists in
  `db/schema.sql` but had no ORM declaration in
  `atlas/modules/identity/models.py`, so the lookup raised `KeyError` and every
  call to `IdentityService.check_scoped_role` failed. In practice that meant
  **every authenticated business request in Atlas returned HTTP 500** — not
  only projects: documents, land, commercial, construction, customer
  lifecycle, finance and reporting all authorise through the same call.

  Found by building the web client, on the first authenticated request ever
  made against a real database through the real identity service. Fixed by
  declaring the association table.

  Why 325 tests missed it, which matters more than the fix: the unit tests
  cover `scoping.py`'s pure grant-interpretation logic, and the Phase 1
  integration tests inject a stub identity that answers the authorisation
  question directly, so nothing ever ran the real `check_scoped_role` against
  PostgreSQL. This is exactly the service-level gap
  `docs/phase-evidence-register.md` warns about, arriving as a production
  defect within a day of that warning being written. Regression coverage added
  in `tests/integration/test_scoped_authorisation.py`.

  Worth acting on beyond the fix: any other `metadata.tables[...]` string
  lookup is the same accident waiting to happen, and the register's
  recommended service-level tests for Phases 3-10 should be taken seriously
  rather than deferred.
- [x] RESOLVED 2026-08-20: **six modules published writes but no reads.**
  Atlas exposed 104 POST endpoints against 11 GET, and change control,
  compliance, construction/quality, customer lifecycle, finance and project
  controls had no GET at all — every change request, RFI, NCR, snag, booking,
  collection, reconciliation and quantity became unreadable the moment it was
  written. Found while building the web client, which could not show a
  register for any of them.

  Added 22 list endpoints, taking the API from 11 GET to 33. All follow the
  existing `Organization.list_projects` pattern: scoped authorisation through
  `check_scoped_role`, archived rows excluded, ordered by their natural key.
  Booking- and batch-scoped reads resolve their parent first and authorise
  against *its* project or entity, so a caller cannot read another project's
  payment history or another entity's ledger by guessing an id.

  Seven new permission codes, granted per module rather than per endpoint:
  `change.read`, `compliance.read`, `construction.read`, `quality.read`,
  `customer.read`, `finance.read`, `project_controls.read`. **Worth an owner
  review**: `construction.read` and `quality.read` are deliberately separate so
  a scheduler can see the programme without seeing defect records, but the
  other five are module-wide, which is coarser than the write permissions they
  sit beside. If finer read scoping is wanted — say, collections readable
  separately from bookings — it is much cheaper to split now than after roles
  are assigned.

  Covered by `tests/integration/test_module_reads.py`, which goes through the
  services rather than around them: each read is checked for what it returns,
  that it refuses an out-of-scope caller, and that it hides archived rows.
  Note the material master is estate-wide and therefore needs a *global*
  grant; an entity-scoped role is correctly refused.

  Still no reads: individual detail endpoints (`GET /ncrs/{id}` and the like),
  installments, registration and possession records, inspection templates,
  material issuances, and the whole commercial module beyond budgets. The
  registers were the blocking gap; these are the next increment.
- [ ] BLOCKING, found 2026-08-20: **Phase 10 still needs logical replication
  and a scheduled materialized-view refresh before go-live.** Originally the
  dashboards returned HTTP 500 on any freshly provisioned database, not stale
  or empty data.
  `db/schema.sql` creates `reporting.mv_ceo_project_summary ... WITH NO DATA`,
  and PostgreSQL refuses to read a materialized view that has never been
  populated — `ObjectNotInPrerequisiteStateError: materialized view
  "mv_ceo_project_summary" has not been populated`. Nothing in the repository
  ever issues `REFRESH MATERIALIZED VIEW`: the only mentions of the view are
  its definition, its ORM mapping, and a line in
  `docs/phase-10-completion-handoff.md` noting that refresh workers "remain
  production" work.

  So the gap itself was known; its consequence was not. "No refresh worker
  yet" implies stale figures. The actual behaviour is that both dashboard
  endpoints fail outright until someone refreshes the view by hand, which is
  the difference between a reporting lag and an outage.

  Compounding it, the reporting database is a *separate* database that Phase 10
  expects to be fed by logical replication, and no replication is configured
  anywhere in the repository. Even after a manual refresh the view aggregates
  whatever the reporting database happens to hold, which on a fresh install is
  nothing.

  Needs, before go-live: logical replication from the transactional database,
  a scheduled refresh (the unique project index already supports
  `REFRESH ... CONCURRENTLY`), and a decision on what the endpoints should do
  when the view is unpopulated — 500 is the wrong answer either way.

  Found by building the dashboards UI. Like the authorisation defect above, it
  was invisible to the suite: the four reporting tests are database-free, and
  no integration test touched the reporting database at all.

  Evidence update 2026-08-23: `test_reporting_database_separation.py` now uses
  two real PostgreSQL databases and proves dashboard aggregates come from the
  reporting database while authorisation stays on the transactional session.
  The test performs an explicit local refresh to isolate that boundary; it does
  not resolve this production refresh/replication blocker, which remains open.

  Mitigation update 2026-08-23: Atlas now checks PostgreSQL's authoritative
  `pg_matviews.ispopulated` flag before dashboard-backed reads. An unpopulated
  view returns a minimized HTTP 503 `reporting_unavailable` response with a
  provisional 60-second `Retry-After`, rather than exposing a driver exception
  as HTTP 500. Owner review is still required for the retry policy and the
  production scheduler; this mitigation does not make unrefreshed data ready.
- [x] DECIDED 2026-08-20 by the repository owner: the frontend stack is
  **React + Vite + TypeScript**, resolving the deferral recorded in
  `docs/phase-1-module-boundaries.md` ("no frontend framework has been
  chosen"). The stated reason for deferring — not building browser UI ahead of
  a tested passkey ceremony — no longer holds now that the WebAuthn routes and
  their tests exist. Lives in `web/`, TypeScript strict with
  `exactOptionalPropertyTypes`, dependency-light by intent.
- [ ] OPEN, owner decision: **where the browser keeps the opaque session
  token.** The web client stores it in `sessionStorage`, which any injected
  script can read. The alternative is an httpOnly, Secure, SameSite cookie,
  which is materially stronger but requires the backend to set and read a
  cookie rather than return the token in a JSON body — an API change, not a
  frontend one. Current mitigation is only that tokens are short-lived and
  server-revocable. Decide before any real data is entered.
- [ ] OPEN, owner decision: **whether owner-console operations should be
  reachable over HTTP at all.** Device approval, break-glass and audit
  verification are CLI-only today, and the web client documents the commands
  rather than performing them. That is a deliberate refusal, not an omission:
  these require `is_owner` plus a fresh step-up, and putting them behind a
  browser session widens the blast radius of a stolen session considerably.
  If a web device-approval queue is wanted, it needs its own design and review.
- [ ] Residual from the above, NOT blocking: PyMuPDF calls in
  `atlas/modules/documents/preview.py` are still effectively untyped — the
  override buys deprecation-safety and a pin, not type coverage. Genuinely
  checking them needs a local stub package. Decide whether that is worth doing;
  it pairs with the Phase 2 renderer-sandboxing item below, since this module
  renders untrusted PDFs.
- [ ] Two integration tests were wrong in ways only a real run could expose, and
  both had been wrong since the phase that introduced them: one inserted a
  `trust_level` value (`'trusted'`) the CHECK constraint has never allowed, and
  one asserted with `scalar_one()` across the whole `identity.sessions` table,
  assuming it was the only test ever to write a session. Treat this as evidence
  that tests which have never been executed are not evidence of anything, and
  require the integration suite to run in CI before any phase is signed off.

## Phase 2 — Documents

- [ ] Select the encrypted object-storage implementation and customer-managed
  key configuration. Opaque object keys are stored in PostgreSQL; filesystem
  paths, public URLs, credentials, and encryption keys are forbidden.
- [ ] Replace `LocalDocumentStorage` before production. Its append-only,
  traversal-resistant, size-limited and SHA-256-verifying behavior is the
  minimum contract the encrypted object-store adapter must preserve.
- [ ] Define permitted upload MIME types, maximum sizes, archive handling, and
  the production malware-scanning engine. Files must remain quarantined until
  scanning succeeds.
- [ ] Define the authoritative SHA-256 calculation point and verify content on
  ingest and retrieval. A revision's binary and checksum are immutable.
- [ ] Review the provisional database invariants: every document must belong to
  a project, revision codes are unique per document, object keys are globally
  unique, and checksums are lowercase SHA-256 values.
- [ ] Approve classification-to-access and retention rules for public,
  internal, confidential, and restricted documents.
- [ ] Review the provisional device rule: restricted document content requires
  an owner-elevated device; all authenticated requests reject session risk
  scores above the platform threshold of 50.
- [ ] Approve dynamic-watermark content and privacy treatment. The provisional
  design will use user ID, session ID, and UTC timestamp—not email, phone, IP,
  or other personal information—unless explicitly approved.
- [ ] Define export-approval thresholds, approver roles, expiry, download
  limits, and whether restricted documents may ever be exported.
- [ ] Review the provisional four-eyes rules: requester and approver must differ,
  approval expires after 15 minutes, downloads require fresh step-up, and each
  approval permits exactly one integrity-checked download.
- [ ] Add an orphan-object reconciliation job. A local object can remain
  unreferenced if filesystem storage succeeds but the database transaction is
  later rolled back; it must be reported and retained until an approved cleanup
  policy exists.
- [ ] Select preview/PDF conversion tooling and sandbox it with no outbound
  network, read-only inputs, resource limits, and disposable working storage.
- [ ] Security-review and sandbox the provisional PyMuPDF preview renderer;
  pin the approved version, fuzz malformed PDFs, cap pages/dimensions/runtime,
  and run conversion in an isolated worker before production use.

## Later phases

- [ ] Add phase-specific decisions here before each phase is declared complete.
- [ ] CRM build-versus-integrate and provider choice remain open until Phase 8.
- [ ] AI hosting, zero-retention DPA or self-hosting, prompt-injection controls,
  confidence thresholds, and authority-boundary red-team remain mandatory
  gates before Phase 11.

## Phase 4 — Budgets, procurement, contracts, and vendor onboarding

- [ ] Approve budget and purchase-order approval thresholds, segregation of
  duties, delegated authority, amendment rules, and four-eyes requirements.
- [ ] Define vendor activation/suspension ownership and verify that no purchase
  order can be issued until onboarding is active and required compliance
  evidence is current.
- [ ] Classify PAN, GST, bank verification, labour registrations, insurance
  policies, contacts, and KYC evidence. Approve masking, retention, access,
  export, breach-notification, and data-subject procedures with legal/privacy
  advisers.
- [ ] Raw KYC, bank proof, cheque images, signatures, credentials, and account
  numbers must never appear in operational fields, logs, fixtures, or audit
  payloads. Store evidence as restricted Documents records with controlled
  preview/export; migrate and remove the provisional `object_storage_key` field
  before production.
- [ ] Select an e-signature provider and approve identity assurance, webhook
  signature verification, replay protection, evidence retention, data
  residency, revocation, provider outage, key rotation, and manual-fallback
  requirements.
  Provisional integrity rule implemented 2026-08-23: execution accepts only a
  non-archived approved/issued Documents record in the contract's project with
  at least one approved/issued immutable revision. Validation goes through the
  published Documents contract and requires the actor to retain document-read
  authority; cross-project, draft, and revision-less evidence fail closed.
- [ ] Approve contract/PO cancellation, supersession, dispute, payment, and
  expiry workflows. Confirm whether issued financial commitments require fresh
  passkey step-up and independent approval.
- [ ] Review provisional invariants: one onboarding record per vendor,
  non-negative monetary/quantity fields, immutable executed-document evidence,
  and archival instead of deletion.

## Phase 5 — Construction, site diary, QA/QC, snagging, and EHS

- [ ] Approve the offline site-diary conflict policy. The provisional design
  uses a client-generated UUID for idempotency, accepts one diary per project
  and calendar date, preserves server versions, and rejects conflicting edits
  rather than silently selecting a winner.
- [ ] Select the approved mobile-device storage and sync design: encrypted
  local database, device binding, remote wipe/revocation behavior, minimum OS,
  TLS pinning decision, retry limits, clock-skew handling, and maximum offline
  retention must be security-reviewed before real field data is cached.
  Provisional local implementation added 2026-08-24: Site Diary payloads are
  AES-256-GCM encrypted before IndexedDB storage with a non-extractable
  browser-generated key. Cleartext queue metadata is limited to queue UUID,
  project UUID, queued timestamp, attempt count, state, and minimized error
  code. Sync runs only in the foreground while an authenticated tab is open;
  no bearer token is stored with drafts. Network failures remain pending,
  successful submissions alone delete drafts, and HTTP client errors move a
  draft to `needs_review` without automatic replay. The service worker caches
  same-origin shell assets only and explicitly excludes `/api` and `/health`.
  Owner/security review is still required: browser CryptoKey storage is not a
  hardware-keystore guarantee, XSS in an authenticated origin can invoke the
  key, private-mode/storage eviction can lose drafts, and remote wipe, device
  binding, retention expiry, retry ceilings, cache-version rollout, minimum
  browser/OS, and field-device UAT are not yet approved.
- [ ] Classify visitor logs, worker counts, incident narratives, assignees,
  photos, location/unit references, and device timestamps. Define minimization,
  notice/consent, retention, access, export, and incident-reporting rules.
- [ ] EHS fatality/major-incident handling requires jurisdiction-specific
  escalation, regulator notification, legal hold, investigation ownership, and
  tamper-evident evidence procedures approved by qualified advisers.
  Provisional integrity/privacy controls implemented 2026-08-23: incident
  transitions serialize on the incident row, follow the ordered state machine,
  and cannot close without recorded corrective action. Audit events record only
  severity, status, version, and whether corrective action exists; they exclude
  the incident narrative and corrective-action text. Confirm the allowed close
  roles, step-up/independent-approval requirements, severity taxonomy, and
  retention/disclosure rules before production use.
- [ ] Approve inspection template governance, required evidence types,
  inspector independence, failed-inspection/NCR escalation, snag severity/SLA,
  rectification verification, and close authority.
  Provisional integrity control implemented 2026-08-23: inspection-template
  and snag transitions lock their rows before evaluating the state machine;
  schedule-activity transitions use the same serialization. PostgreSQL tests
  prove incompatible concurrent transitions produce one committed winner and
  rollback removes both the transition and audit event. Confirm who may retire
  templates, complete activities, rectify/verify/close snags, and which actions
  require independent approval or fresh step-up.
  Provisional scope rule implemented 2026-08-23: project-specific templates,
  predecessor activities, linked diaries/inspections/progress, and all supplied
  building/floor/unit coordinates must belong to the target project; global
  templates remain allowed. PostgreSQL composite foreign keys protect links
  that carry both project IDs, while the published Organization contract checks
  inherited location scope and hierarchy consistency. Confirm whether global
  templates should remain enabled and who may publish or retire them.
  Provisional no-code builder implemented 2026-08-24: project drafts expose
  structured checklist rows and evidence-required toggles, draft edits lock the
  row and require an exact expected version, stale concurrent writers fail,
  checklist content stays out of audit payloads, and activation removes the
  draft from the editable builder. Confirm template-copy/global-template
  governance, activation authority, post-activation correction/supersession,
  checklist content classification, and maximum checklist complexity.
- [ ] Site photos, certificates, inspection reports, and progress evidence must
  use restricted Documents records. Raw binaries, public URLs, GPS metadata,
  biometric data, and personal identifiers must not be embedded in JSON fields,
  logs, fixtures, or audit payloads.
  Provisional progress-evidence rule implemented 2026-08-23: the evidence must
  be an unarchived Documents record in the activity's project with at least one
  revision in `virus_scanned`, `under_review`, `approved`, or `issued`; draft,
  quarantined, cross-project, archived, missing, unauthorised, and unconfigured
  validation fail closed. Confirm whether `virus_scanned` alone is sufficient
  for submitted progress, or whether reviewer approval must be mandatory.
  The same provisional rule now applies to inspection and snag evidence.
  Inspection completion serializes on the inspection row and deduplicates
  repeated document IDs. Confirm required evidence types/counts per checklist,
  whether `under_review` evidence may support final completion, and whether a
  failed inspection or critical snag requires independent review or step-up.
- [ ] Review provisional progress invariants: percentage is 0–100, one update
  per activity/date, schedule dates cannot run backwards, and progress evidence
  remains immutable after submission.
  Provisional integrity control implemented 2026-08-23: writers serialize on
  the schedule-activity row, and every accepted update must have a strictly
  later date and a percentage no lower than the latest update. Notes stay out
  of audit payloads. Confirm whether same-date retries should remain conflicts
  or become idempotent, whether corrections require a separate supersession
  workflow, and which roles may submit or correct progress before go-live.
- [ ] Choose the authoritative project/site business timezone and date rollover
  policy. The local service currently derives automatic transition dates from
  UTC; do not assume UTC calendar dates match the legally relevant site date.
- [ ] Approve the provisional Phase 5 archival policy implemented 2026-08-23.
  Activities must be completed, EHS incidents closed, templates retired,
  inspections completed, and snags closed before archival. Submitted diaries
  and individual progress updates may be archived without changing lifecycle
  state. Archival is row-locked, idempotent, versioned, and audited in the same
  transaction; audit payloads contain only version and archival timestamp.
  Confirm retention/legal-hold exceptions, whether diary/progress correction
  needs a supersession workflow, and who may archive each record type.
- [ ] Grant and review the new least-privilege archive permissions before any
  non-test deployment: `construction.schedule.archive`,
  `construction.progress.archive`, `construction.diary.archive`,
  `construction.ehs.archive`, `quality.template.archive`,
  `quality.inspection.archive`, and `quality.snag.archive`. No production role
  assignment is selected in source.
- [ ] Confirm that archived progress remains part of the monotonic progress
  history. The service intentionally includes archived updates when checking
  later percentages, so archival cannot enable a lower replacement value.
- [ ] Approve the provisional construction-meeting policy implemented
  2026-08-24. Meetings are `recorded` then `closed`; action items are `open`,
  `overdue`, or `done`. New actions serialize on the meeting row, closed or
  archived meetings reject new actions, and closure requires every active
  action to be done. Confirm whether a meeting with zero actions may close,
  who may mark an action overdue/done, whether the responsible user must be the
  completer, and whether closure needs independent approval or fresh step-up.
- [ ] Classify meeting participant references, decisions, and action
  descriptions. The provisional API accepts participant user UUIDs only,
  returns participant/decision counts in meeting summaries, and excludes
  decisions and action descriptions from audit payloads. Content remains in
  PostgreSQL behind scoped access; approve encryption, retention, legal hold,
  export, redaction, and disclosure rules before real meeting content is used.
- [ ] Decide how meeting participants and action owners are validated. Database
  foreign keys validate action-owner identity existence, but the service does
  not yet prove that participant UUIDs are active users or that participants
  and responsible users belong to the project's authorized organization scope.
- [ ] Grant and review the provisional meeting permissions before deployment:
  `construction.meeting.create`, `construction.meeting.action.create`,
  `construction.meeting.action.update`, `construction.meeting.close`,
  `construction.meeting.archive`, and
  `construction.meeting.action.archive`. Reads currently use the shared
  `construction.read` permission. No production role assignment is selected in
  source.

## Phase 6 — BIM, quantities, WBS, and material traceability

- [ ] Select and security-review the IFC/BIM validation and extraction tooling,
  sandboxing limits, file-size/time limits, malware scanning, parser patching,
  and failure quarantine behavior before accepting real model files.
  The provisional API added 2026-08-24 accepts only 1-5,000 structured object
  mappings for an already validated import; it does not accept or parse model
  bytes, paths, URLs, or credentials. Before production, approve a least-
  privilege extraction worker identity, signed extraction provenance, chunking
  and retry rules for larger models, correction/supersession semantics, and the
  boundary between automated mapping and mandatory human review.
- [ ] Classify BIM models, object GUIDs, room/unit mappings, quantities, rates,
  and derived geometry as confidential project intellectual property. Approve
  access, watermark/export, retention, legal hold, and vendor-processing rules.
  Structured GUIDs and room references are returned only through the scoped
  BIM read permission, but their classification and export policy remain an
  owner decision.
- [ ] Migrate and classify legacy free-form BIM source references into the new
  restricted Documents foreign key. New writes use only Documents evidence;
  never accept local paths, credentials, signed URLs, or public object URLs.
- [ ] Approve CostCode hierarchy governance, code ownership, maximum depth,
  re-parenting rules, and whether codes are project-specific or reusable master
  data. The provisional schema prevents duplicate project codes only.
- [ ] Approve quantity units, conversions, rounding precision, tolerance policy,
  verifier independence, discrepancy escalation, and final approval authority.
  Phase 7 owns formal discrepancy/change workflows.
  Provisional enforcement added 2026-08-24: the approving user must differ from
  the verifier attribution stored in `updated_by`. Confirm the production role
  matrix, legacy attribution remediation, step-up requirements, and whether
  dedicated immutable verifier/approver columns are required instead of this
  existing attribution field.
- [ ] Define material master ownership and duplicate-merging rules. The current
  `(name, unit_of_measure)` uniqueness is provisional and not a substitute for
  an approved SKU/catalogue identity strategy.
  Structured BIM material mappings currently require an active global material
  master; materials have no project ownership in the canonical schema. Confirm
  that scope model before production. The `asset` BIM object type has no asset-
  master foreign key because no asset domain exists yet; approve asset identity/
  lifecycle ownership before treating that mapping as production asset
  integration.
- [ ] Classify supplier batch/lot references, test certificates, recipient/site
  allocation notes, and issuance evidence; set minimization, access, retention,
  export, and legal-hold rules. Evidence must be restricted Documents records.
  Provisional enforcement added 2026-08-24: BIM imports require a same-project,
  unarchived document with a malware-cleared-or-later revision; material receipt
  certificates and issuance evidence require a same-project, unarchived document
  with an approved or issued revision. Missing/unavailable Documents integration
  fails closed before mutation. Confirm the accepted revision states, document
  types/classifications, approval authority, certificate expiry/revocation, and
  whether issuance evidence is mandatory by material/category or threshold.
- [ ] Approve stock reservation and concurrency policy. Issuance must lock the
  source receipt and reject cumulative quantities above the accepted receipt;
  decide whether rejected/partial receipts, returns, transfers, wastage, and
  unit conversion require separate immutable ledger event types.
  Evidence update 2026-08-23: PostgreSQL tests prove the receipt row remains
  locked across authorization and cumulative summing, a concurrent issuer
  blocks, and only one of two competing 60-of-100 issuances commits. The
  provisional receipt-level serialization remains subject to owner approval
  alongside reservation, return, transfer, and unit-conversion policy.
- [ ] Review the database-enforced same-project invariant between material
  receipts and purchase orders, including how legacy rows should be remediated
  before migration. The migration fails closed rather than attaching a receipt
  to a purchase order in another project.
  Migration `0015_phase6_scope_integrity` extends this fail-closed rule to BIM
  source documents and objects, CostCode/quantity links, receipt certificates,
  issuance evidence, and issuance receipt/project/material identity. Before
  applying it to a populated environment, inventory all legacy null or
  cross-project references, approve remediation evidence, rehearse lock time
  and rollback, and retain a signed exception report. The migration backfills
  only a null BIM-object project from its referenced import; it does not guess
  how to repair contradictory non-null ownership.
  Migration `0016_phase6_bim_mapping` adds nullable work-package/material
  mappings and a material foreign key. Rehearse the migration on a production-
  shaped copy and approve legacy object classification before backfilling.

## Phase 7 — Change management, RFIs, NCRs, and discrepancies

- [ ] Approve the change-control authority matrix, financial thresholds,
  segregation of requester/reviewer/approver, required impact reviews, quorum,
  rejection/rework rules, and which transitions require fresh passkey step-up.
  The provisional service enforces requester/approver separation.
  Integrity update 2026-08-24: the state path now includes the Blueprint's
  schedule-impact and customer-impact reviews; transitions serialize on the
  workflow row. Confirm that the fixed sequence, rejection availability from
  every pre-approval stage, and terminal archive permissions match the approved
  authority matrix.
- [ ] Classify change descriptions, schedule/budget impacts, quotations, RFIs,
  responses, defects, corrective actions, and discrepancy explanations. Define
  least-privilege access, retention, legal hold, export, and redaction rules.
- [ ] Require controlled Documents evidence for drawings, quotations,
  calculations, site photos, test reports, responses, and closure proof. Legacy
  JSON/free-form evidence references must be migrated; never store raw files,
  public URLs, credentials, signatures, or personal data in workflow JSON.
  Provisional enforcement added 2026-08-24: every new or replacement evidence
  ID must be active, same-project, and have a malware-cleared-or-later revision;
  change approval and discrepancy resolution require an approved or issued
  revision. Composite PostgreSQL constraints fail closed across all four Phase
  7 tables. Confirm accepted revision states by evidence type, document
  classification, expiry/revocation rules, and whether RFI/NCR closure must
  always carry separate closure evidence. Inventory legacy cross-project rows
  before migration `0017_phase7_workflow_integrity`; rehearse locks, failure,
  rollback, and signed exception handling on a production-shaped copy.
- [ ] Approve RFI routing and SLA policy by discipline/severity, overdue clock
  source and site timezone, reassignment/escalation rules, response authority,
  and whether a response can be superseded without a new immutable revision.
- [ ] Approve NCR severity, regulator/client notification, corrective-action
  ownership, independent reinspection, closure authority, recurrence tracking,
  and legal-hold rules for major or critical defects.
  Provisional closure now requires an active same-project inspection whose
  status is `completed` and result is `pass`; the referenced inspection row is
  locked through the published Construction contract until the transaction
  completes. Confirm whether the reinspector must differ from the original
  inspector, NCR raiser, corrective-action owner, and closer, and whether failed
  reinspections create a new NCR or another immutable reinspection attempt.
- [ ] Approve quantity discrepancy thresholds, required engineering/commercial
  reviewers, owner-approval triggers, resolution authority, and linkage to
  budgets, procurement, contracts, and change requests. No automatic financial
  posting is implemented until those policies are decided.
- [ ] Decide notification recipients and message minimization. Email/SMS/push
  notifications must contain opaque workflow IDs and safe summaries only, with
  no confidential narrative, evidence URL, token, or personal information.
- [ ] Approve retention and archival policy for closed/rejected changes, closed
  RFIs/NCRs, and resolved discrepancies. The provisional API archives only
  terminal records, is idempotent, increments version once, writes one minimized
  audit event, and never deletes the business row. Confirm retention periods,
  legal-hold overrides, restoration policy, export treatment, and production
  role assignments for `change.archive`, `quality.rfi.archive`,
  `quality.ncr.archive`, and `quality.discrepancy.archive`.

## Phase 8 — Customer booking, collections, registration, possession, and e-sign

- [ ] Resolve the Blueprint §25 CRM build-versus-integrate decision. Customer
  lifecycle work does not select a CRM vendor or expand the provisional lead
  table; approve data ownership, synchronization, consent, and deletion rules.
- [ ] Classify customer/party identity, KYC, contact data, booking documents,
  payment schedules, collection references, registration instruments,
  possession evidence, and signed contracts. Approve purpose, consent/notice,
  residency, retention, correction, export, legal hold, and erasure handling.
- [ ] Keep PAN/Aadhaar/passport, bank account, cheque image, payment credentials,
  signatures, signature certificates, and provider tokens out of source, logs,
  fixtures, audit payloads, and free-form reference fields. Store approved
  evidence only in restricted Documents records.
- [ ] Select and review the payment-collection integration, PCI scope, webhook
  signature verification, replay/idempotency controls, settlement matching,
  bounce/refund/chargeback workflow, and secret rotation before real payments.
- [ ] Approve booking authority, unit hold/expiry policy, cancellation/refund
  rules, joint ownership, nominee handling, transfer/resale, pricing/tax rules,
  and the provisional invariant of one non-cancelled booking per unit.
  Provisional fail-closed rule implemented 2026-08-24: a booking may not be
  cancelled directly after any active payment plan, collection, registration,
  possession, or executed-contract link exists. Define compensating
  cancellation, refund, reversal, unit-release, and approval workflows before
  enabling real bookings.
- [ ] Approve payment-plan rounding, installment allocation order, partial and
  excess collections, waivers, overdue timezone, interest/penalty, receipts,
  segregation of collection/allocator roles, and immutable correction entries.
  Provisional integrity rule implemented 2026-08-23: installment creation locks
  its payment-plan row before summing active installments, so concurrent
  requests cannot jointly exceed the plan total. Collection allocation already
  locks the target installment and refuses cumulative allocation above its
  amount. PostgreSQL tests cover sequential and concurrent refusal. Owner review
  remains required for rounding, waivers, excess-funds handling, and corrections.
  Receipt-time validation now also refuses an installment from another booking;
  decide whether unallocated receipts are permitted and how later allocation,
  bounce, refund, chargeback, and immutable correction entries are authorized.
- [ ] Select the e-signature provider and approve signer authentication,
  consent, certificate validation, callback verification, timestamp authority,
  evidence retention, revocation, and provider outage/manual fallback policy.
  Evidence update 2026-08-23: booking linkage fails closed unless the Commercial
  contract belongs to the same project and customer, is executed, and carries
  controlled execution evidence. PostgreSQL tests cover wrong-project,
  wrong-customer, unexecuted, missing-evidence, and valid audited linkage.
  Provider authenticity and certificate validation remain owner-gated.
- [ ] Approve registration and possession prerequisites, government reference
  handling, snag clearance, customer acceptance, handover evidence, key/access
  credential transfer, and independent authorization for final handover.
  Provisional rules implemented 2026-08-24 serialize registration and
  possession transitions on the booking row, require registration before
  possession, and require active same-project controlled evidence with an
  `approved` or `issued` revision for final registration, handover, and contract
  linkage. Booking/collection evidence accepts `virus_scanned`, `under_review`,
  `approved`, or `issued` revisions. Confirm whether pre-approval evidence is
  sufficient for money-receipt records and require independent final approvers
  if segregation of duties is desired.
- [ ] Approve the Phase 8 database-versus-service enforcement boundary.
  PostgreSQL now enforces booking-document/project scope, active-unit uniqueness,
  and core foreign keys. Unit/project ancestry, collection/installment booking
  ownership, and registration/possession evidence project scope are checked by
  the audited service because the current normalized tables do not carry the
  duplicate project key needed for a simple composite foreign key. Decide
  whether to retain this boundary, add denormalized project keys, or commission
  reviewed constraint triggers before production writes are enabled.
- [ ] Approve customer-record archival and retention roles. Phase 8 exposes no
  delete path, but terminal booking, plan, installment, collection,
  registration, possession, and contract-link archival/retention periods still
  require legal, finance, privacy, and audit-owner sign-off before go-live.

## Phase 9 — Tally import and reconciliation

- [ ] Decide whether Phase 9 integrates Tally, ERPNext, or another accounting
  system. ERPNext is provisionally an external/self-hosted accounting system
  behind an Atlas finance adapter, not a replacement for Atlas's PostgreSQL
  domain model, passkey/session security, scoped authorization, controlled
  Documents, or hash-chained audit. Before selection, approve system-of-record
  ownership, chart-of-accounts and legal-entity mapping, API authentication,
  least-privilege service accounts, webhook signing/replay protection,
  idempotency, reconciliation and correction semantics, availability/DR,
  upgrade compatibility, data residency, GPL-3.0 obligations, and exit/export
  strategy. A wholesale Frappe/ERPNext rebuild requires a separate architecture,
  security, privacy, migration, licensing, and cost review and is not authorized
  by the accounting-provider decision alone.
- [ ] Approve the exact Tally export formats, supported Tally versions, company
  and legal-entity mapping, fiscal periods, currency/tax treatment, and how an
  export is proven complete before a batch may be validated.
  Provisional integrity rule implemented 2026-08-23: validation locks the batch
  and refuses any pending batch that already contains voucher rows. Voucher
  import uses the same lock, preventing application-level validation/import
  races. PostgreSQL tests prove refusal leaves status, validation summary,
  version, and audit chain unchanged. Owner approval is still required for the
  authoritative completeness manifest and partial-file recovery policy.
- [ ] Keep Tally credentials, license details, bank data, narration, party tax
  identifiers, unrestricted exports, and raw provider payloads out of source,
  logs, fixtures, HTTP bodies, and audit events. Source exports must remain in
  restricted Documents storage with approved classification and retention.
- [ ] Approve the ledger-mapping taxonomy, maker-checker permissions, effective
  dates, ambiguity handling, retirement/versioning, and independent review of
  mappings before real reconciliation runs.
- [ ] Approve matching tolerances, date windows, rounding, partial/split/merged
  vouchers, reversals, credit notes, duplicate detection, cross-project
  allocation, and every discrepancy type. Current behavior creates explicit
  cases and never silently treats a mismatch as reconciled.
- [ ] Approve accountant reviewer roles, segregation of duties, resolution
  codes, evidence requirements, accepted-exception authority, reopen/correction
  policy, and retention of review notes before production use.
- [ ] Design the background import queue with authenticated job submission,
  malware/content validation, bounded parsing, idempotency, retry/backoff,
  dead-letter visibility, operator cancellation, and resource limits.
- [ ] Decide whether any future Tally connector may be read-only or bidirectional.
  Atlas currently has no posting capability; any write-back requires a separate
  threat model, approval workflow, credential custody design, and owner sign-off.

## Phase 10 — CEO dashboard and advanced analytics

- [ ] Provision and validate the logical-replication reporting replica. Approve
  publication/subscription scope, replication credentials, network isolation,
  encryption, lag alerts, failover behavior, RPO/RTO, backup/restore, and a hard
  guarantee that dashboard credentials cannot write to the primary.
- [ ] Approve each dashboard metric definition, source-of-truth field, timezone,
  currency, tax treatment, rounding, freshness indicator, refresh SLA, and how
  incomplete or stale data is displayed instead of silently treated as current.
- [ ] Approve cash-horizon assumptions; receivable/payable and margin formulas;
  contractor score weights; sales-velocity windows; inventory-aging start date;
  delay, overrun, inspection, collection, compliance, and decision thresholds.
- [ ] Classify dashboard aggregates for inference and re-identification risk.
  Restrict legal-entity/project drill-downs and prohibit party/customer identity,
  tax IDs, bank/payment references, document text, narratives, and raw Tally
  payloads from materialized views, caches, logs, URLs, and exports.
- [ ] Approve report formats, watermarking, step-up authentication, export size
  limits, malware-safe generation, temporary storage encryption, signed-link
  lifetime, download audit, retention/destruction, and whether scheduled reports
  may ever be delivered outside the in-app controlled-download flow.
- [ ] Design the refresh/scheduler worker with idempotency, bounded concurrency,
  retry/backoff, dead-letter visibility, cancellation, refresh locking, query
  timeouts, resource limits, and alerts for failed or stale materialized views.

## Phase 11 — Private AI assistant

- [ ] OWNER GATE: choose either a self-hosted open-weight model or a commercial
  provider under an executed enterprise zero-retention DPA. Approve hosting
  location, subprocessors, residency, training/retention terms, deletion,
  incident notification, audit rights, availability, and exit/portability. The
  provider remains deliberately disabled until this is signed off.
- [ ] For self-hosting, approve model/license, signed weight provenance, malware
  scanning, isolated runtime, GPU/CPU capacity, patch cadence, network egress
  denial, model rollback, supply-chain verification, and secrets-free images.
  For commercial hosting, approve private networking, scoped credentials,
  rotation/revocation, request signing, TLS validation, rate/cost limits, and a
  verified zero-retention configuration.
- [ ] Approve the provisional `0.80` minimum confidence threshold per intent and
  evaluate calibration on representative synthetic and legally reviewed cases.
  Low-confidence model text is currently withheld rather than shown as advice.
- [ ] Expand prompt-injection testing beyond deterministic signals to indirect
  injection in PDFs, drawings, emails, OCR, encoded text, multilingual content,
  tool output, retrieval poisoning, instruction smuggling, and multi-turn/chained
  attacks. Maintain a versioned red-team corpus and independent sign-off.
- [ ] Approve retrieval sources, chunking, classification inheritance, scope
  filtering before retrieval, evidence citation rules, freshness, revocation,
  poisoning detection, and the rule that retrieved content is data—not system
  instruction. No raw document text is currently accepted by the HTTP API.
- [ ] Approve request/response retention and lawful-purpose rules. AI tables and
  audit events currently persist only digests, lengths, scope IDs, enumerated
  action/reason codes, confidence, and statuses; raw prompts/responses are not
  persisted and must not enter logs, traces, analytics, or crash reports.
- [ ] Approve human review and escalation for recommendations and proposed tasks,
  including segregation of duties and evidence. Permanently forbid AI approval,
  payment release, message sending, final budget/quantity/drawing changes,
  permission/device approval, signing, and deletion at every provider/tool layer.
- [ ] Establish model monitoring, drift/bias testing, abuse detection, rate and
  token limits, cost alerts, kill switch, incident response, rollback, audit-log
  review, provider outage behavior, and periodic reauthorization of the model.

## Phase 3 — Land, legal, financing, and compliance

- [ ] Approve the due-diligence checklist taxonomy, mandatory categories,
  waiver authority, and evidence-retention rules with qualified legal counsel.
- [ ] Review which land, title, lender, RERA, PDC, and statutory records contain
  personal or regulated financial data; restrict fields, exports, logs, and
  retention accordingly.
- [ ] Confirm that lender names and reference numbers are operational metadata
  only. Bank account numbers, cheque images, credentials, and payment secrets
  must remain in classified document storage or the accounting system of record.
- [ ] Approve loan-default, bounced-PDC, overdue-obligation, approval-expiry,
  and RERA-lapse escalation thresholds and notification recipients.
- [ ] Review the provisional invariant that each loan has at most one EMI/PDC
  installment of a given type per due date; revise if business practice permits
  split instruments.
