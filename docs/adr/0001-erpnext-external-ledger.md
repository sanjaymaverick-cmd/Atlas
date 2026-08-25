# ADR 0001: Integrate ERPNext as an external ledger

- Status: accepted for local development
- Date: 2026-08-24

## Context

Atlas needs a free, self-hosted statutory accounting system. The prior Phase 9 design assumed Tally exports. Rebuilding Atlas on Frappe would discard the verified security, workflow, evidence, and audit foundation and would couple every domain to ERPNext's DocTypes. Building a statutory ledger inside Atlas would create unacceptable tax, accounting, localization, and upgrade risk.

## Decision

Keep Atlas and ERPNext as separate deployables and systems of record. Atlas owns operational intent, approvals, evidence, mappings, synchronization state, reconciliation, and audit. ERPNext owns submitted accounting documents, statutory books, financial statements, and the India Compliance extension where validated.

The `finance` module publishes provider-neutral DTOs and contracts. A concrete ERPNext adapter translates only at the boundary and uses supported authenticated HTTP APIs. No Atlas code writes ERPNext or Frappe database tables directly. Initial integration is read-only; posting remains disabled until its separate approval, idempotency, segregation-of-duties, and UAT gates are accepted.

## Consequences

- ERPNext/Frappe upgrades and schema details are isolated behind one adapter.
- Atlas and ERPNext require independent backup, restore, security, and availability operations.
- Cross-system consistency is eventual and must use idempotency keys, durable outbox/inbox state, retry limits, and reconciliation.
- Company, fiscal year, chart of accounts, party, tax, project, cost-centre, currency, and voucher mappings require explicit versioned approval.
- ERPNext, Frappe, India Compliance, GST/GSP, and third-party service licences and terms require owner/legal review before production.
- A future ledger replacement implements the same narrow contract without redefining Atlas domains.
