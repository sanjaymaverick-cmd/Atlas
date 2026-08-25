# Phase 5 module boundaries

Phase 5 adds a `construction` module covering schedule activities, daily progress, offline-capable site diary intake, EHS incidents, inspection templates and executions, evidence links, and snag lifecycles.

The module depends only on the published Identity contract and platform audit writer. Its public surface is `contracts.py` plus immutable DTOs in `schemas.py`; ORM models and service implementation are private. HTTP routers only validate and translate requests before calling that contract.

All mutations use the caller's database transaction for the record and hash-chained audit event. Narrative fields that may contain personal, safety, or commercially sensitive information are excluded from audit payloads. Evidence is referenced by Documents UUID rather than stored as binary data or a public URL.

Phase 6 owns BIM, BOQ, quantities, material traceability, and CostCode WBS. Phase 7 owns changes, RFIs, NCRs, and discrepancy cases; none are silently implemented here.
