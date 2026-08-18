# Phase evidence register

Built 2026-08-18 to support handover item 4, "re-record the Phase 1-10
sign-offs on the basis of the now-passing integration coverage."

This document records **what the test suite actually evidences, per phase**, so
that a sign-off is made against a concrete list rather than against "the suite
passes." It is deliberately not a sign-off itself: nothing here attests that a
phase is complete. That judgement is the owner's, and this register exists to
make it an informed one.

Counts are from `pytest --collect-only` on 2026-08-18: 278 unit tests, 39
integration tests, 317 total, 0 skipped when `ATLAS_TEST_DATABASE_URL` is set.

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

| Phase | Module(s) | Integration | Unit | Route |
| --- | --- | ---: | ---: | ---: |
| 1 — identity, org, audit, owner console | `identity`, `organization`, `audit`, `platform` | **36** | 166 | yes |
| 2 — documents | `documents` | **2** | 24 | yes |
| 3 — land, compliance | `land`, `compliance` | **0** | 4 | 1 |
| 4 — commercial | `commercial` | **0** | 5 | 1 |
| 5 — construction, QA/QC | `construction` | **0** | 7 | 1 |
| 6 — project controls | `project_controls` | **0** | 3 | 1 |
| 7 — change control | `change_control` | **0** | 4 | 1 |
| 8 — customer lifecycle | `customer_lifecycle` | **0** | 3 | 1 |
| 9 — Tally reconciliation | `finance` | **0** | 3 | 1 |
| 10 — reporting | `reporting` | **0** | 4 | 1 |
| 11 — AI safety | `ai_assistant` | **0** | 19 | 1 |
| cross-cutting | schema / migrations | **1** | — | — |

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

- **Phase 4** — "purchase orders cannot be issued until the vendor is active",
  and executed contracts require immutable document evidence.
- **Phase 6** — "material issuance is serialized against its receipt and rejects
  cumulative quantities above accepted stock"; the composite
  `(id, project_id)` foreign keys that stop cross-project references.
- **Phase 8** — "more than one active booking per unit" is prevented by the
  partial unique index `uq_active_booking_unit`, which only a real database can
  enforce; likewise installment and collection over-allocation, and linkage to
  an unexecuted or wrong-customer contract.
- **Phase 9** — the `uq_reconciliation_fact` unique index and the guard that
  refuses import when pre-existing Tally vouchers are present.
- **Phase 10** — that aggregate reads use the distinct read-replica session and
  never the transactional one. The route test asserts the wiring; nothing
  asserts the behaviour against two real databases.
- **All phases 3-10** — the blueprint-wide invariants: every mutation writes its
  audit event *in the same transaction*, optimistic versioning holds under
  concurrency, and archival replaces deletion. Phase 1 proves these for
  `organization.projects`. Nothing proves them for the other domains.

## What sign-off is defensible today

A fair reading of the evidence:

- **Phase 1** — re-record the sign-off. The database-backed behaviour is now
  genuinely exercised, and the tests are pointed at the things that matter.
- **Phase 2** — re-record with the narrowness noted; two integration tests is
  thin for the size of the phase.
- **Phases 3-10** — **do not re-record on the basis of integration coverage,
  because there is none.** Either sign off explicitly on the weaker basis
  (service-level unit tests and route-thinness tests, with the database-enforced
  rules untested and named as such), or commission integration tests for the
  invariants listed above first. The second is the honest path if these phases
  are meant to be "verified" in the sense Phase 1 now is.
- **Phase 11** — not eligible; it remains a fail-closed foundation pending the
  Blueprint §25 hosting decision.

## Suggested next step

The gap is concrete and finite. One integration test per phase, aimed at that
phase's single most important database-enforced invariant — the ones listed
above — would take Phases 3-10 from "asserted" to "evidenced" at a cost of
roughly eight tests. That is a much smaller job than it looks, because the
fixtures, the schema, and the audit-verification helpers already exist and are
proven by the Phase 1 suite.

Recorded so the choice is deliberate rather than inherited.
