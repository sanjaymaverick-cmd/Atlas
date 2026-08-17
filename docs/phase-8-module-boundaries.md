# Phase 8 module boundaries

Phase 8 adds `customer_lifecycle` for bookings, payment plans and installments, collections and allocation, registration, possession, and linkage to executed customer contracts.

The module publishes only `contracts.py` and immutable DTOs. It may call Organization's published unit/project validator and Commercial's published contract lookup; it cannot import either module's models or services. This prevents cross-project unit bookings and verifies that a linked contract belongs to the booking customer/project and already has immutable execution evidence.

Every mutation writes a same-transaction hash-chained audit event, including secondary booking/installment mutations. Bank/payment references, customer PII, signatures, and narrative documents are excluded from audit payloads. Evidence is represented only by restricted Documents UUIDs.

The open CRM build-versus-integrate choice, payment provider, e-sign provider, regulatory registration rules, and possession authority remain explicit owner-review items in `production-readiness-todo.md`.
