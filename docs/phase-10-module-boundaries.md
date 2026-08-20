# Phase 10 module boundaries

Phase 10 adds a read-only `reporting` module for the CEO dashboard, advanced
analytics, and controlled report generation.

The Phase 0.5 decision is binding: production reporting reads use a separately
injected PostgreSQL logical-replication read-replica session and materialized
views in the `reporting` schema. Reporting queries must never receive or reuse
the transactional primary session. Local tests may inject a synthetic reporting
contract or an explicitly marked disposable reporting session.

The reporting module publishes immutable aggregate DTOs. It may depend on
Identity contracts for scoped authorization and platform audit/database
services, but never on another business module's models or service internals.
Materialized views are the only cross-domain read boundary.

Dashboard responses contain aggregates and opaque record IDs only. They exclude
party/customer names, contact details, tax identifiers, bank/payment references,
document contents, free-form narratives, and raw accounting exports. Report
generation is human-triggered, scoped, non-mutating, and audit-recorded on the
transactional primary; no report result is silently emailed or published.

The initial production-shaped metrics cover project financial position,
delivery/compliance risk, inventory and sales state, and open reconciliation
exceptions. Forecasting formulas, contractor score weights, sales-velocity
windows, inventory-aging definitions, refresh SLA, and export retention remain
owner-review decisions recorded in `production-readiness-todo.md`.
