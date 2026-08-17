# Phase 9 Completion Handoff

Phase 9 implements controlled Tally import evidence, normalized voucher facts,
explicit discrepancy cases, and accountant review while preserving Tally as the
statutory book of record. Atlas has no Tally posting or voucher-amendment path.

## Integrity and privacy controls

- Source exports remain restricted Documents records referenced by UUID and a
  lowercase SHA-256 digest; raw export payloads are not accepted by the API.
- Import batches and review transitions are serialized with database row locks.
- Duplicate export content, voucher external IDs, and reconciliation facts are
  rejected, including cases whose Tally voucher reference is null.
- Every mutation, including the parent batch transition caused by first voucher
  ingestion, writes a same-transaction audit event.
- Ledger names, voucher numbers, and resolution narratives are not copied into
  audit payloads; safe recorded/not-recorded indicators are used instead.
- Reconciliation uses explicit open, review, reconciled, and accepted-exception
  states. A final outcome requires a coded resolution and increments version.

## Verification on 2026-08-17

- Ruff lint passed; Ruff format check passed for 175 files.
- Strict mypy passed for 137 source files.
- Import-linter kept all 21 contracts with 0 broken across 137 files.
- Full pytest collected 290 tests: 252 passed and 38 PostgreSQL-dependent tests
  skipped because `ATLAS_TEST_DATABASE_URL` was unavailable. Skips were not
  counted as passes.
- Bandit found no medium/high-severity issues across 17,869 lines and used no
  `#nosec` suppressions.
- pip-audit found no known vulnerabilities; the local non-PyPI `atlas` package
  was correctly reported as unauditable.
- Alembic has one head: `0010_phase9_tally_reconciliation`.

PostgreSQL-backed integration execution remains required before production.
All unresolved matching, mapping, connector, access-control, retention, and
accounting-policy decisions are recorded in `production-readiness-todo.md`.
