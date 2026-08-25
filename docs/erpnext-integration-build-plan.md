# ERPNext integration build plan

This plan replaces the former Tally-specific Phase 9 direction. Each stage must pass its gates before the next begins.

## 9A — Boundary and migration

- Adopt the External Ledger glossary and system-of-record matrix.
- Rename canonical Phase 9 persistence and APIs to provider-neutral terms.
- Add an idempotent Alembic migration for databases created before this decision.
- Preserve controlled source-document evidence, SHA-256 deduplication, reconciliation uniqueness, and same-transaction audit.

Gate: baseline schema, upgraded schema, service contracts, API tests, and architecture contracts agree.

## 9B — ERPNext read-only proof of concept

- [x] Implement the narrow authenticated HTTP construction boundary using
  `SecretsProvider`, HTTPS enforcement, a localhost-only development exception,
  redirect refusal, bounded timeouts/connections, streamed response-size limits,
  snapshot-preserving pagination cursors, and redacted errors.
- [ ] Wire the adapter into a background sync worker; no API request may perform
  a long-running ERPNext synchronization inline.
- Read synthetic Company/account/project and submitted voucher facts from a pinned supported ERPNext version.
- Normalize provider data into External Vouchers without storing unrestricted payloads.
- Verify reruns are idempotent and failed pages cannot mark a batch complete.

Gate: synthetic contract tests and a disposable local ERPNext environment prove completeness, replay, refusal, and observability.

## 9C — Mapping and reconciliation

- Add effective-dated, four-eyes mappings for companies, accounts, parties, projects/cost centres, taxes, currencies, and document types.
- Reconcile opening/closing trial balance, P&L, balance sheet, receivables/payables ageing, inventory, bank state, GST, and source-document counts.
- Require signed exception disposition and immutable control-total evidence.

Gate: zero unexplained differences in the agreed synthetic migration corpus.

## 9D — Approval-gated posting

- Add a durable outbox and immutable posting receipts.
- Separate requester, approver, and accounting roles; require fresh step-up for high-risk releases.
- Use one Atlas idempotency key per business intent and verify the ERPNext result before completion.
- Keep posting disabled by configuration until production-readiness approval.

Gate: duplicate, timeout, partial failure, reversal, period-close, and permission tests pass.

## 9E — Staging, migration rehearsal, and cutover

- Pin versions and deploy isolated Atlas/PostgreSQL and ERPNext/MariaDB stacks.
- Exercise backup/restore, secret rotation, monitoring, rate limits, and rollback.
- Import only supported customer-controlled legacy exports; never reverse-engineer proprietary storage.
- Run parallel books for the approved period and obtain accountant, tax, security, privacy, and owner sign-off.

Gate: every Phase 9 production TODO is resolved and evidence is retained before live data or credentials are introduced.
