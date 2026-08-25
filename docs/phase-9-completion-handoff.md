# Phase 9 redesign handoff

The former provider-specific reconciliation slice has been redesigned around a provider-neutral External Ledger boundary, with ERPNext selected as the first separately deployed adapter. Atlas remains the security, workflow, evidence, mapping, reconciliation, and audit control plane; ERPNext owns statutory accounting documents and reports.

## Preserved controls

- Controlled Documents UUID and lowercase SHA-256 provenance; unrestricted exports are not accepted by the API.
- Row-locked sync validation and voucher ingestion.
- Unique export digests, external voucher IDs, and reconciliation facts, including null external references.
- Same-transaction audit for every Atlas mutation and versioned review transition.
- Audit redaction for account names, voucher numbers, remote payloads, credentials, and resolution narrative.

## Redesigned surface

- Canonical tables: `ledger_sync_batches`, `ledger_account_mappings`, `external_vouchers`, and `reconciliations`.
- Public routes use `/ledger-sync-batches`; DTOs use Atlas/external-ledger vocabulary.
- Discrepancies use `missing_in_external_ledger` and `missing_in_atlas`.
- `0019_erpnext_external_ledger` migrates databases created under the former names while preserving the historical Alembic revision chain.
- `ExternalLedger` is the narrow provider-neutral contract; `ERPNextLedgerAdapter` is a bounded, read-only HTTP implementation with synthetic contract tests.
- `ERPNextConnectionConfig` constructs the client from `SecretsProvider`
  references. It requires HTTPS except for an explicit localhost development
  exception, refuses redirects, bounds timeouts/connections and response bytes,
  and never accepts credentials through an Atlas HTTP request.
- Pagination freezes a UTC creation watermark in an opaque cursor, so records
  created during a multi-page run do not shift its offset window. The future
  worker must persist the cursor and fail closed on missing or partial pages.

## Next gate

Continue Stage 9B from `erpnext-integration-build-plan.md`: add the durable
background sync state machine, then verify it against a disposable, pinned local
ERPNext + India Compliance environment. Prove pagination completeness, replay,
partial failure, version compatibility, and reconciliation using synthetic data.
Do not add live credentials or enable write-back.
