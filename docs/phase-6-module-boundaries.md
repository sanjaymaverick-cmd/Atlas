# Phase 6 module boundaries

Phase 6 adds the `project_controls` module for controlled BIM import registration and validation, CostCode WBS creation, quantity verification and approval, and receipt-linked material issuance.

Only `contracts.py` and immutable DTOs in `schemas.py` are published. ORM mappings and service implementation are private. The module depends on Identity's published authorization contract and the platform audit writer; it does not reach into Documents internals. Evidence is represented by Documents UUIDs.

Every mutation and its hash-chained audit event share the request transaction. Material issuance locks its source receipt and checks cumulative non-archived issuance before writing. Quantity discrepancies stop at `discrepancy`; Phase 7 owns formal discrepancy, change, RFI, and NCR resolution.

New writes use `source_document_id`; the mandatory legacy `source_file_reference` receives the same UUID string only for backward schema compatibility. Existing free-form rows must be migrated before use. API callers cannot provide storage paths, signed URLs, credentials, or raw BIM content.
