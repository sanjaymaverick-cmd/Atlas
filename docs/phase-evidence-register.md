# Phase evidence register

Built 2026-08-18 to support handover item 4, "re-record the Phase 1-10
sign-offs on the basis of the now-passing integration coverage."

**Updated 2026-08-23.** Phase 3 now has service-level PostgreSQL coverage for
the blueprint-wide same-transaction audit invariant. A real `LandService`
parcel creation is proved to commit with exactly one valid hash-chain event,
and an explicit rollback is proved to remove both the parcel and its audit
event. This closes that invariant for Phase 3 only; it does not imply the same
coverage for Phases 4-10.

The post-change full suite passed with **337 tests and zero skips** against the
real disposable PostgreSQL 16 database. This count includes newer authenticated
read/UI coverage added after the original 2026-08-18 count below.

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
  by `test_commercial_service_audit.py` against PostgreSQL. Executed contracts
  requiring immutable document evidence is still service-level and remains
  open, as do concurrency/versioning and archival evidence for the phase.
- **Phase 6** — ~~the composite `(id, project_id)` foreign keys~~ now covered.
  Still open: "material issuance is serialized against its receipt and rejects
  cumulative quantities above accepted stock", which is a service-level check
  over accumulated rows, not a constraint.
- **Phase 8** — ~~more than one active booking per unit~~ now covered, both the
  rejection and the release-on-cancel. Still open: installment and collection
  over-allocation, and linkage to an unexecuted or wrong-customer contract.
- **Phase 9** — ~~`uq_reconciliation_fact`~~ now covered, including the NULL
  voucher path. Still open: the guard that refuses import when pre-existing
  Tally vouchers are present.
- **Phase 10** — the project-scope check on report requests and the distinct
  reporting-database read path are now covered. The latter test provisions two
  real databases, seeds the dashboard project only in reporting, and proves
  authorisation remains on primary while the aggregate comes from reporting.
  The production logical-replication, refresh worker, and unpopulated-view
  behaviour remain open go-live gates.
- **Phases 4-10** — still mostly open for the largest remaining gap: the
  blueprint-wide service invariants. Every mutation writes its audit event *in
  the same transaction*, optimistic versioning holds under concurrency, and
  archival replaces deletion. Phase 1 proves these for
  `organization.projects`; Phase 3 proves commit/rollback atomicity for
  `land.land_parcels`; Phase 4 now proves it for purchase-order issuance. The
  other domain-invariant tests exercise constraints directly and deliberately
  bypass the service layer where these guarantees live. Concurrency/versioning
  and archival coverage outside Phase 1 also remain open.

## What sign-off is defensible today

A fair reading of the evidence:

- **Phase 1** — re-record the sign-off. The database-backed behaviour is now
  genuinely exercised, and the tests are pointed at the things that matter.
- **Phase 2** — re-record with the narrowness noted; two integration tests is
  thin for the size of the phase.
- **Phases 3-10** — each now has one integration test proving its strongest
  database-enforced rule. Phases 3 and 4 additionally have one focused
  service-level transaction slice. This is a real improvement on nothing but
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

Next, in rough order of risk: resolve the known Phase 10 unpopulated-view outage
without pretending local refresh is production replication, then Phase 8's
over-allocation checks and Phase 4's executed-contract evidence gate.

Recorded so the choice is deliberate rather than inherited.
