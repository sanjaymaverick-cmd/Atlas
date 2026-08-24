# Phase 9 module boundaries

Phase 9 adds `finance` as Atlas's provider-neutral External Ledger boundary. It owns controlled sync evidence, normalized External Vouchers, mappings, deterministic reconciliation facts, review lifecycles, and—only after a future owner gate—approved posting intent and receipts.

ERPNext is a separate statutory book of record. Frappe DocTypes, authentication, paging, error formats, and version quirks stay inside `ERPNextLedgerAdapter`. Finance services consume `ExternalLedger` DTOs; API routers remain thin and never call ERPNext directly. Atlas never reads or writes ERPNext/MariaDB tables.

`finance` may depend on published Identity contracts and platform audit/database services. It must not import another business module's models or service internals. Earlier modules and the owner console may import only finance contracts and DTOs, never finance models, services, or adapters.

The current adapter is deliberately read-only. Posting requires a durable outbox, immutable receipt, stable idempotency key, maker-checker approval, step-up policy, recovery semantics, and an explicit production-readiness decision.

Raw external responses, narration, credentials, bank data, tax identifiers, and unrestricted exports are excluded from API payloads, logs, audit events, and normalized tables. Controlled source documents remain in Documents; finance stores their UUID and SHA-256 provenance only.
