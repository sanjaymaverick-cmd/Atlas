# Phase evidence register

Built 2026-08-18 to support handover item 4, "re-record the Phase 1-10
sign-offs on the basis of the now-passing integration coverage."

**Updated 2026-08-23.** Phase 3 now has service-level PostgreSQL coverage for
the blueprint-wide same-transaction audit invariant. A real `LandService`
parcel creation is proved to commit with exactly one valid hash-chain event,
and an explicit rollback is proved to remove both the parcel and its audit
event. This closes that invariant for Phase 3 only; it does not imply the same
coverage for Phases 4-10.

The latest post-change full suite passed with **398 tests and zero skips**
against the real disposable PostgreSQL 16 database. This count includes newer
authenticated read/UI and phase-specific service coverage added after the
original 2026-08-18 count below.

This document records **what the test suite actually evidences, per phase**, so
that a sign-off is made against a concrete list rather than against "the suite
passes." It is deliberately not a sign-off itself: nothing here attests that a
phase is complete. That judgement is the owner's, and this register exists to
make it an informed one.

Counts are from `pytest --collect-only` on 2026-08-18: 278 unit tests, 47
integration tests, 325 total, 0 skipped when `ATLAS_TEST_DATABASE_URL` is set.

**Updated later the same day.** The gap this register identified has since been
partly closed: `tests/integration/test_phase_domain_invariants.py` adds one
integration test per phase for Phases 3-10, each pinned to that phase's
strongest database-enforced rule. The original finding and the remaining gap
are both preserved below, because what is *still* unevidenced matters more to a
sign-off than what is now covered.

## Read this before signing anything

The handover states that with the integration suite now passing, "the behaviour
is evidenced now, but it was not when those phases were declared complete."
That is true for **Phase 1**. It is **not** true for Phases 3-10.

All 38 pre-existing integration tests concentrate on Phase 1 (36 tests) and a
two-test slice of Phase 2. **Phases 3, 4, 5, 6, 7, 8, 9, 10 and 11 have no
integration tests at all.** Their coverage is database-free: a handful of
service unit tests against mocks, plus exactly one HTTP route test each, and
those route tests assert the adapter is thin and rejects bad input — they do
not exercise the business rule behind it.

This matters because Atlas deliberately puts its integrity in the database.
`docs/local-postgres.md` says so directly: the behaviour under test — the
hash-chain trigger, the append-only triggers, the CHECK constraints — lives in
the database, and a mock would only assert that the mock behaves as written. A
database-free test cannot evidence a database-enforced rule.

So the fix to the integration suite genuinely upgraded the evidence for Phase 1.
It did not change the evidentiary position of Phases 3-10 at all, because there
was never anything there to run.

## Per-phase evidence

"Integration" below shows the count as originally found, then as it stands after
the Phase 3-10 invariant tests were added.

| Phase | Module(s) | Integration | Unit | Route |
| --- | --- | ---: | ---: | ---: |
| 1 — identity, org, audit, owner console | `identity`, `organization`, `audit`, `platform` | **36** | 166 | yes |
| 2 — documents | `documents` | **2** | 24 | yes |
| 3 — land, compliance | `land`, `compliance` | 0 → **3** | 4 | 1 |
| 4 — commercial | `commercial` | 0 → **1** | 5 | 1 |
| 5 — construction, QA/QC | `construction` | 0 → **1** | 7 | 1 |
| 6 — project controls | `project_controls` | 0 → **1** | 3 | 1 |
| 7 — change control | `change_control` | 0 → **1** | 4 | 1 |
| 8 — customer lifecycle | `customer_lifecycle` | 0 → **1** | 3 | 1 |
| 9 — Tally reconciliation | `finance` | 0 → **1** | 3 | 1 |
| 10 — reporting | `reporting` | 0 → **1** | 4 | 1 |
| 11 — AI safety | `ai_assistant` | **0** | 19 | 1 |
| cross-cutting | schema / migrations | **1** | — | — |

### What the Phase 3-10 invariant tests prove

One test each, in `test_phase_domain_invariants.py`, each asserting that a
violation is *rejected* and naming the constraint that rejected it — so a test
cannot pass by tripping a different rule on the same table:

| Phase | Rule now evidenced |
| --- | --- |
| 3 | a RERA registration number cannot be claimed by two projects |
| 4 | a vendor cannot hold two onboarding records |
| 5 | a replayed site-diary entry is rejected by its device idempotency key |
| 6 | material cannot be received against another project's purchase order |
| 7 | an NCR cannot cite an inspection belonging to another project |
| 8 | a unit cannot be actively booked twice, and cancelling releases it |
| 9 | the same reconciliation fact cannot be raised twice, NULL voucher included |
| 10 | a project-scoped report cannot be requested without a project |

Phase 8's test also asserts the positive case, because the guarantee is a
*partial* unique index: after the first booking is cancelled the unit must
become bookable again. A blanket unique index would satisfy the rejection and
fail that, so both halves are needed to pin the actual behaviour.

Phase 1's 166 unit tests are `identity` (72) plus the `platform` services every
phase relies on (94: step-up 24, access control 21, secrets 18, backup 16, audit
chain 15). The 36 `api` tests are counted once under Phase 1/2 and are the
source of the per-phase "route" column.

### What the Phase 1 integration tests actually prove

These are the only tests that exercise real PostgreSQL behaviour, and they are
substantive:

- `test_audit_hash_chain_integrity.py` (8) — chain survives multi-row
  transactions and concurrent writers; writer timezone does not break
  verification; UPDATE and DELETE are rejected *by the database*; the verifier
  detects both a row edited behind the triggers and a deleted row.
- `test_project_crud_audit.py` (9) — every mutation writes exactly one event;
  updates record prior values and bump the version; a failed mutation writes no
  event; scoping refusals; archive-not-delete.
- `test_owner_console_cli.py` (9) — audit verify exits non-zero on a broken
  chain; device approval requires the owner; break-glass seal/invoke/revoke.
- `test_break_glass_flow.py` (7) — holder invokes without the owner; non-holder
  cannot; a used credential cannot be reused; revocation kills sessions.
- `test_session_token_auth.py` (3) — the stored value is a hash and the plain
  token is not stored; expired and revoked tokens are rejected.

That is a real basis for re-recording the Phase 1 sign-off.

### What Phase 2's two integration tests cover

`test_document_revision_audit.py` covers revision-and-archive versioning with
audit, and that a duplicate revision code rolls back without writing a second
event. Real, but narrow: the storage layer, malware-quarantine states,
watermarked previews, and four-eyes export approval are evidenced only by
database-free tests.

## Specific claims that remain unevidenced

The README describes behaviour for Phases 3-10 that is enforced wholly or partly
by the database, and therefore is not exercised by any currently passing test.
These are the ones worth resolving before a sign-off, because each is a rule the
system is *claimed* to guarantee:

Struck-through items are now covered by `test_phase_domain_invariants.py`. The
rest are still open, and they are the ones that matter for a sign-off.

- **Phase 4** — the application-only vendor-active purchase-order gate and the
  purchase-order issue/audit commit and explicit-rollback paths are now covered
  by `test_commercial_service_audit.py` against PostgreSQL. Contract execution
  now uses the published Documents contract and refuses cross-project,
  archived/unapproved, or revision-less evidence; the valid controlled-evidence
  path and same-transaction audit commit are covered too. Broader
  concurrency/versioning and archival evidence remains open for the phase.
- **Phase 5** — EHS incident transitions now lock the incident row, enforce the
  ordered state machine, and refuse closure unless corrective action is already
  recorded. PostgreSQL tests prove invalid-transition refusal, serialized
  concurrent assignment, same-transaction audit commit/rollback, and that
  incident narratives and corrective-action text are excluded from the audit
  payload. Jurisdiction-specific escalation, notification, retention, and
  close-authority policy remain owner/adviser gates. Schedule-progress writers
  now lock the activity row and accept only strictly later, non-decreasing
  updates. PostgreSQL tests prove chronological/percentage refusal, serialized
  concurrent writers, minimized audit commit, and explicit rollback. Controlled
  progress evidence now uses the published Documents contract and requires a
  same-project, unarchived document with a malware-cleared-or-later revision;
  cross-project, draft, quarantined, archived, and unconfigured validation paths
  fail closed. The same published-contract rule now covers inspection and snag
  evidence. Inspection completion additionally locks the inspection row;
  PostgreSQL tests prove concurrent finalization produces one final state and
  one audit event, while valid evidence rows and audit commit or roll back
  together. Inspection notes and snag descriptions remain outside audit
  payloads. Activity, inspection-template, and snag transitions now lock their
  rows before evaluating the state machine. Parameterized PostgreSQL tests
  prove incompatible concurrent transitions produce one winner and that each
  lifecycle's state/version and audit event roll back together. Composite
  PostgreSQL foreign keys now reject cross-project activity predecessors, EHS
  diaries, progress activities, and snag inspections. Service tests additionally
  reject cross-project/archived templates and inconsistent building-floor-unit
  hierarchies through the published Organization contract while preserving
  global templates. Empty-database migration equivalence covers the new DDL.
  All seven Phase 5 record types now have row-locked, idempotent archival service
  methods and thin HTTP adapters. Activities, EHS incidents, templates,
  inspections, and snags must be terminal before archival; progress updates and
  submitted diaries retain their current state. Parameterized PostgreSQL tests
  prove one version increment and one minimized valid audit event on commit,
  no row or audit change on rollback, no duplicate event on retry, and refusal
  for every nonterminal lifecycle state covered by the service policy.
  Creation-path evidence now covers activities, site diaries, EHS incidents,
  inspection templates, scheduled inspections, and snags as well: each commits
  exactly one domain row and one valid privacy-minimized audit event, while an
  explicit rollback removes both. Progress creation retains its separate
  chronological, monotonic, evidence, rollback, and concurrency suite.
  Meeting registers/action items now have a service/API layer too. Meeting
  creation, action creation, ordered action transitions, closure, reads, and
  terminal archival are scoped and audited. The meeting row lock serializes
  action creation with closure; closure refuses unfinished actions. PostgreSQL
  tests cover commit/rollback, minimized audit payloads, idempotent archival,
  concurrent create-versus-close, and the composite project foreign key.
  Canonical DDL and sole migration head `0014_phase5_meeting_integrity` are
  equivalent from an empty database. The two explicit Blueprint UX carryovers
  are now implemented too. The Site Diary browser encrypts payloads before
  IndexedDB storage, retains conflicts without silent overwrite, deletes only
  after successful foreground sync, stores no session token with drafts, and
  uses an API-excluding runtime shell cache. The no-code QA/QC builder supports
  dynamic checklist/evidence rows, project-draft reload/edit with expected
  versions, and activation. Browser tests cover encrypted-at-rest structure,
  non-extractable keys, sync retention/removal, privacy-minimized capture, and
  version-aware builder updates; production build and npm audit are CI gates.
- **Phase 6** — the composite `(id, project_id)` foreign keys and cumulative
  material-issuance guard are now covered. A two-session PostgreSQL test proves
  the second issuer blocks on the receipt lock and only one competing 60-of-100
  issuance succeeds; sequential overdraw and valid audit commit are covered.
  BIM sources, receipt certificates, and issuance evidence are now resolved
  through the published Documents contract before mutation. Ten PostgreSQL
  cases prove cross-project, draft, and archived evidence is refused unchanged;
  malware-cleared BIM and approved/issued certificate or issuance evidence
  commit atomically with a valid privacy-minimized audit event. Canonical DDL
  and migration `0015_phase6_scope_integrity` now enforce project scope across
  BIM source/object, CostCode/quantity, certificate, and issuance references,
  plus receipt project/material identity. Direct SQL adversarial coverage proves
  all seven invalid linkage shapes fail. BIM and quantity transitions row-lock
  before authorization/state evaluation; two-session tests prove one winner,
  and rollback tests prove state/version/audit atomicity. Returns, transfers,
  wastage, unit conversion, and BIM-object import remain open workflow work.
- **Phase 8** — active-unit double booking, installment-total over-allocation,
  and collection-to-installment over-allocation are now covered against
  PostgreSQL. Concurrent installment additions are serialized on the payment
  plan, proving two individually valid requests cannot jointly exceed its
  total. Booking-contract linkage now has PostgreSQL coverage for wrong project,
  wrong customer, unexecuted/no-evidence refusal, and valid audited linkage.
  Broader transaction/version/archive coverage remains open.
- **Phase 9** — `uq_reconciliation_fact` and the pending-batch pre-existing
  voucher guard are now covered. Validation and voucher import both lock the
  batch row; PostgreSQL tests prove a contaminated pending batch is refused
  unchanged and clean validation commits or rolls back with its audit event.
  Background parsing, full-file completeness, and production Tally integration
  remain deployment/workflow gates.
- **Phase 10** — the project-scope check on report requests and the distinct
  reporting-database read path are now covered. The latter test provisions two
  real databases, seeds the dashboard project only in reporting, and proves
  authorisation remains on primary while the aggregate comes from reporting.
  The same test proves an unpopulated view is refused explicitly; HTTP tests
  prove the refusal is a minimized retryable 503 rather than an internal error.
  Production logical replication and the refresh worker remain open go-live
  gates.
- **Phases 4-10** — still mostly open for the largest remaining gap: the
  blueprint-wide service invariants. Every mutation writes its audit event *in
  the same transaction*, optimistic versioning holds under concurrency, and
  archival replaces deletion. Phase 1 proves these for
  `organization.projects`; Phase 3 proves commit/rollback atomicity for
  `land.land_parcels`; Phase 4 proves it for purchase-order issuance, and Phase
  5 proves it for EHS corrective-action assignment, schedule-progress creation,
  inspection completion, and activity/template/snag transitions. The other
  domain-invariant tests exercise constraints directly and deliberately
  bypass the service layer where these guarantees live. Concurrency/versioning
  coverage and archival coverage outside Phases 1 and 5 remain open.

## What sign-off is defensible today

A fair reading of the evidence:

- **Phase 1** — re-record the sign-off. The database-backed behaviour is now
  genuinely exercised, and the tests are pointed at the things that matter.
- **Phase 2** — re-record with the narrowness noted; two integration tests is
  thin for the size of the phase.
- **Phases 3-10** — each now has one integration test proving its strongest
  database-enforced rule. Phases 3, 4, 6, 8, 9, and 10 additionally have focused
  service-level or database-boundary slices. This is a real improvement but
  is still materially weaker than Phase 1's coverage. Defensible to re-record
  **scoped to the named rules**: "the unit double-booking guarantee is
  evidenced" is now true; "Phase 8 is verified" is not. The remaining
  service-layer guarantees — same-transaction audit, optimistic versioning,
  cumulative checks, and workflows — are where most of the business logic
  lives. Sign off on specific rules, not whole phases, until that coverage is
  built.
- **Phase 11** — not eligible; it remains a fail-closed foundation pending the
  Blueprint §25 hosting decision.

## Suggested next step

The eight database-invariant tests are done. The remaining gap has shifted from
"no integration coverage" to "no *service-level* integration coverage", and it
is the more valuable half.

The highest-return pieces identified here are now complete for Phase 3 and the
first Phase 4 service slice. `test_land_service_audit.py` proves commit and
explicit rollback atomicity for land-parcel creation;
`test_commercial_service_audit.py` proves the application-only vendor-active
purchase-order gate plus issue/audit commit and explicit rollback. Continue
phase by phase rather than extrapolating either domain's proof to the others.

Next, continue the remaining phase-by-phase service transaction,
concurrency/version, and archival proofs, prioritizing workflows that change
financial, legal, safety, or customer state.
Phase 10 production replication and refresh scheduling stay in the
owner-reviewed deployment register rather than being simulated in code.

Recorded so the choice is deliberate rather than inherited.
