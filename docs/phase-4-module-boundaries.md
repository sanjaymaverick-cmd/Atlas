# Phase 4 module boundaries

The Commercial module owns budget, procurement, contract, vendor-onboarding,
KYC, insurance, and labour-compliance workflows. Other modules may import only
`atlas.modules.commercial.contracts` and `atlas.modules.commercial.schemas`.
ORM mappings and services are private.

The module depends on Identity's published scoped-role contract and platform
audit/database services. It does not import Organization or Documents internals.
Project, party, vendor, contractor, and evidence-document identifiers remain
opaque UUIDs whose referential integrity is owned by canonical PostgreSQL DDL.

Budget, purchase-order, onboarding, contract, insurance, and labour states use
explicit transition maps. Every mutation increments its version and writes a
redacted audit event in the same transaction. Raw KYC and banking evidence is
never copied into audit state.

Purchase-order issuance requires an active vendor-onboarding record. Contract
execution requires an execution method and a Documents evidence UUID. These
invariants live in the service, not the FastAPI router, and are covered by
database-free service tests. `.importlinter` enforces the module boundary.
