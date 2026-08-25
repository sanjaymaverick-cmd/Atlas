# Atlas project goal

Build Atlas as a private, self-hosted control plane for a multi-entity real-estate development group. Atlas owns identity, scoped authorization, approvals, project and operational workflows, controlled evidence, and tamper-evident audit history. ERPNext is a separately deployed statutory accounting ledger reached only through Atlas's published, provider-neutral external-ledger boundary.

## Completion outcome

- Every business mutation is versioned and audited in the same PostgreSQL transaction.
- Documents and sensitive evidence remain access-controlled, integrity-checked, and excluded from logs and audit payloads.
- ERPNext exchanges are authenticated, idempotent, observable, and reconciled; Atlas never writes directly to ERPNext's database.
- Accounting mappings, posting requests, receipts, discrepancies, and cutover evidence are independently reviewable.
- Each phase is completed and verified before the next begins.
- Local and CI gates cover formatting, lint, strict typing, architecture contracts, unit tests, PostgreSQL integration tests, web tests, dependency audit, and migration equivalence.
- Production remains fail-closed until every owner decision in `docs/production-readiness-todo.md` is approved.

Only synthetic fixtures belong in this public-development repository. Real business data, credentials, tax identifiers, bank details, personal information, production URLs, and secret material are prohibited.
