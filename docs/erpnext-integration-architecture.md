# ERPNext integration architecture

## System-of-record boundary

| Concern | Authoritative system |
|---|---|
| Users, passkeys, sessions, scoped roles, step-up | Atlas |
| Legal entities, projects, operational workflows and approvals | Atlas |
| Controlled documents, decision evidence, audit chain | Atlas |
| Submitted accounting documents, ledgers, trial balance and statutory reports | ERPNext |
| Cross-system mappings, sync state, discrepancies and approvals | Atlas |

ERPNext is not an Atlas database module. It is an untrusted external dependency even when self-hosted.

## Module shape

`finance` depends on a small `ExternalLedger` protocol expressed only in Atlas DTOs. `ERPNextLedgerAdapter` owns Frappe authentication, resource names, pagination and response translation. Routers call finance services; services enforce access, lifecycle, idempotency and audit; only the adapter performs network I/O.

## Read flow

1. An authorized user registers a controlled source document or starts a bounded sync.
2. Atlas creates a digest-addressed Ledger Sync Batch.
3. The worker requests submitted ERPNext facts page by page with a stable watermark.
4. Atlas validates legal entity, currency, mapping version and completeness before atomically accepting normalized External Vouchers.
5. Deterministic reconciliation creates or updates discrepancy facts; reviewers cannot silently overwrite them.

## Future posting flow

1. An Atlas mutation records approved operational intent and a durable outbox item in one transaction.
2. A worker submits the mapped request with a stable idempotency key.
3. The adapter records a sanitized response digest and immutable Posting Receipt.
4. Atlas verifies the resulting ERPNext document and reconciles it. Timeouts remain unknown—not failed—until queried by idempotency key.

## Security and failure controls

- Credentials are secret references injected at runtime; none are accepted through APIs, persisted in business tables, logged, or committed.
- Require HTTPS with certificate verification outside disposable local development; pin allowed origins and block redirects and arbitrary URLs.
- Use a least-privilege ERPNext service identity per environment and legal-entity scope where supported.
- Apply bounded connect/read timeouts, response limits, pagination caps, retry budgets, circuit breaking, and structured metrics without payloads.
- Treat all external strings as untrusted; enforce schemas, lengths, currencies, dates, decimal precision, and permitted document states.
- Never copy narration, tax IDs, bank data, attachment bodies, access tokens, or personal data into audit events.
- Failed or partial synchronization cannot advance the watermark or mark a batch validated.
- Atlas and ERPNext backups are independent; reconciliation watermarks and receipts are required for recovery.

## Deployment

Atlas remains Python/FastAPI/PostgreSQL. ERPNext/Frappe/MariaDB is a separate pinned stack and network zone. Only the integration worker can reach its API. Browser clients never receive ERPNext credentials or call ERPNext directly.
