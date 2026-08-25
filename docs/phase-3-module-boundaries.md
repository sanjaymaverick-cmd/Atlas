# Phase 3 module boundaries

## Land

The Land module owns parcels, due-diligence items, land/legal approvals, loan
obligations, and scheduled EMI/PDC instruments. Consumers use only
`atlas.modules.land.contracts` and `atlas.modules.land.schemas`; ORM mappings and
service implementation are private.

Acquisition, approval, loan, and installment states move through explicit
one-way transitions. Every mutation increments `version` and appends its audit
event in the caller's database transaction. Records are never physically
deleted.

## Compliance

The Compliance module owns RERA registrations and scoped statutory obligations.
Consumers use only its published contract and DTOs. A record must have a project
or legal-entity scope, and authorization is checked against that scope before
mutation.

## Dependency direction

Both modules depend on the Identity contract for scoped-role decisions and on
platform audit/database services. Neither imports Organization internals,
Document internals, or the other Phase 3 module. Due-diligence evidence uses an
opaque document UUID enforced by canonical PostgreSQL DDL rather than importing
Document ORM mappings.

These boundaries are enforced in `.importlinter`. FastAPI routers are
composition adapters only and contain no business lifecycle logic.
