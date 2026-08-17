# Phase 8 Resume Handoff

## Checkpoint scope

- Branch: `phase-1-foundation`
- Stable starting commit: `091e96e` (`Complete local Phase 7 change control`)
- Current slice: Phase 8 customer lifecycle
- Repository remains synthetic-data-only. `.claude/settings.local.json` is intentionally untracked and untouched.

## Implemented in this checkpoint

- Canonical DDL and Alembic migration `0009_phase8_customer_lifecycle` for customer lifecycle records.
- Customer booking creation and cancellation with one-active-booking-per-unit enforcement.
- Payment plans, installments, collection recording, and allocation with row locking and over-allocation protection.
- Registration and possession transitions with controlled evidence references.
- Executed-contract linking through the published Commercial contract.
- Same-transaction audit events, version increments, archival behavior, and payment-reference redaction.
- Thin FastAPI adapters and strict request/response schemas under `/api/v1`.
- Published Organization and Commercial contracts needed by the new module.
- Import-linter boundaries, unit/API tests, README guidance, module-boundary documentation, and production-readiness TODO entries.

## Verification completed

- Targeted customer lifecycle tests: 3 passed.
- Targeted API and customer lifecycle tests: 35 passed.
- Ruff lint: passed.
- Ruff format check: 163 files already formatted.
- Strict mypy: passed for 128 source files using a temporary Linux-side source copy because mounted-drive WSL execution stalled.
- Alembic migration `0009_phase8_customer_lifecycle` was previously confirmed as the sole head.

## Resume sequence

Phase 8 is a checkpoint, not yet declared complete. Resume with these gates in order:

1. Run the full import-linter gate and resolve any contract violations.
2. Run the complete pytest suite; report PostgreSQL-dependent skips separately when `ATLAS_TEST_DATABASE_URL` is unavailable.
3. Run Bandit and pip-audit.
4. Reconfirm Alembic has one head and inspect the final diff for schema/migration parity.
5. Fix any failures, review security/privacy/integrity TODO entries, and make a Phase 8 completion commit.
6. Only after Phase 8 passes every gate, begin Phase 9 Tally reconciliation. Do not silently decide the open CRM build-versus-integrate question.

## Local environment note

No Atlas-specific Python, pytest, mypy, or import-linter process was found on Windows at suspension time. WSL did not start and returned `E_ACCESSDENIED`, so it is not consuming verification CPU from this checkpoint.
