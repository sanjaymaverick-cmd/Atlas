# Atlas domain glossary

**Atlas** — The control plane and system of record for identity, authorization, project operations, approvals, controlled evidence, reconciliation decisions, and hash-chained audit events.

**External Ledger** — A separately deployed accounting system accessed through a narrow Atlas contract. It owns statutory accounting entries and financial statements.

**ERPNext** — The selected External Ledger implementation. Frappe and ERPNext concepts stay inside the adapter and do not define Atlas domain models.

**Ledger Sync Batch** — An immutable, digest-addressed unit of external-ledger facts imported for validation and reconciliation.

**External Voucher** — A normalized, read-only accounting fact obtained from the External Ledger. It is not an Atlas posting instruction.

**Account Mapping** — An effective, owner-approved relationship between an external-ledger account or dimension and an Atlas reference.

**Posting Request** — A future, approval-gated, idempotent request for the External Ledger to create a document. It is never a direct database write.

**Posting Receipt** — The immutable result returned by the External Ledger, including its identifier, status, and request idempotency key.

**Reconciliation Fact** — A deterministic discrepancy between an Atlas fact and an External Voucher, reviewed through an explicit lifecycle.

**Cutover** — The approved transition from a legacy ledger to ERPNext after control totals, statutory evidence, retention, rollback, and owner sign-off gates pass.
