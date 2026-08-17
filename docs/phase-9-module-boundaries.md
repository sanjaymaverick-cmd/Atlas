# Phase 9 module boundaries

Phase 9 adds `finance` for controlled Tally import evidence, normalized voucher facts, ledger mappings, deterministic discrepancy cases, and accountant review.

Tally remains the statutory accounting book of record. Atlas does not post, amend, approve, or delete Tally vouchers. The module stores no unrestricted raw export payload; source files remain controlled Documents records and only their document ID and SHA-256 digest cross the finance boundary.

`finance` may depend on Identity contracts and platform audit/database services. Earlier business modules must not depend on finance internals. Cross-module ERP reference validation will be added only through published contracts, without importing another module's models or service internals.
