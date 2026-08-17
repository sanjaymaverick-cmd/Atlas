# Phase 10 Completion Handoff

Phase 10 implements separated-store CEO dashboard aggregates and queued,
audited report requests. Production startup requires distinct transactional and
reporting database URLs; aggregate queries receive only the reporting session.

## Behavior and controls

- `reporting.mv_ceo_project_summary` aggregates project financial, collection,
  delivery, compliance, reconciliation, and unit-state measures from opaque IDs
  and non-negative facts. It contains no identity, contact, tax, bank, document,
  free-form narrative, or raw Tally fields.
- Materialized-view totals use independent aggregates to prevent join
  multiplication. A unique project index supports concurrent refresh design.
- Project and legal-entity dashboards authorize against the transactional
  primary but query only the injected reporting session.
- Production refuses an identical `ATLAS_DATABASE_URL` and
  `ATLAS_REPORTING_DATABASE_URL`; readiness checks both databases without
  exposing either address or credential.
- PDF/XLSX report requests are queued on the primary, scope-checked against the
  reporting view, versioned, and audited in the same transaction. HTTP requests
  do not synchronously generate, publish, email, or expose report content.

## Verification on 2026-08-17

- Ruff lint passed; Ruff format check passed for 187 files.
- Strict mypy passed for 146 source files.
- Import-linter kept all 23 contracts with 0 broken across 146 files.
- Full pytest collected 296 tests: 258 passed and 38 PostgreSQL-dependent tests
  skipped because `ATLAS_TEST_DATABASE_URL` was unavailable. Skips were not
  counted as passes.
- The final startup-resource ordering correction passed focused Ruff, strict
  mypy, and all 3 default-factory tests.
- Bandit found no medium/high-severity issues across 18,574 lines and used no
  `#nosec` suppressions.
- pip-audit found no known vulnerabilities; the local non-PyPI `atlas` package
  was correctly reported as unauditable.
- Alembic has one head: `0011_phase10_reporting`.

PostgreSQL integration, logical-replication provisioning, materialized-view
refresh workers, and controlled report rendering/download remain production
readiness work and are explicitly recorded in `production-readiness-todo.md`.
Phase 11 must not begin until its AI-hosting decision is owner-approved.
