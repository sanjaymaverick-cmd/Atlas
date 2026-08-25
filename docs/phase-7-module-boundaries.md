# Phase 7 module boundaries

Phase 7 adds `change_control` for change requests, RFIs, NCRs, and quantity discrepancy cases. Its published surface is `contracts.py` and immutable DTOs in `schemas.py`; ORM mappings and service implementation are private.

The module uses only Identity's published authorization contract and the platform audit writer. It stores evidence as restricted Documents UUIDs without importing Documents internals. Narrative questions, responses, descriptions, impacts, corrective actions, and proposed resolutions are excluded from audit payloads.

State machines fail closed. Change approval requires evidence; RFI responses are restricted to the routed recipient; NCR closure requires a reinspection; discrepancy resolution requires evidence. Every mutation and audit event share one transaction.

Cross-module automatic postings and notifications are deferred until the authority, privacy, threshold, and message-minimization decisions in `production-readiness-todo.md` are approved.
