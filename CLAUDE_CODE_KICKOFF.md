# Claude Code Kickoff — Atlas ERP, Phase 0.5 → Phase 1

Paste this into Claude Code at the root of this repository to begin implementation.

---

## Prompt

You are starting implementation on **Atlas**, a private, self-hosted ERP for a multi-entity real estate development group. This is not a greenfield brainstorm — the architecture is already decided. Your job is to build against it, not redesign it.

Read these first, in order, before writing any code:

1. `docs/ERP_Technical_Blueprint_v2.docx` — the full architecture. This supersedes an earlier v1.0; every section is either "carried over unchanged" or marked `NEW`/`Revised` with the audit finding it closes. Pay particular attention to:
   - Section 2 (Architecture Principles) — especially "Private by default," "Human approval for material actions," and "No silent overwrites." These are hard constraints on everything you build, not aspirations.
   - Section 8 (Workflow Engine) — the generic state machine (`Draft → Submitted → Under Review → Clarification Required → Resubmitted → Approved → Contract Execution → Executed → Closed`) that every approval-gated object in this system follows.
   - Section 15 (Security Model) and Section 17 (AI Architecture) — the four-level AI authority model (Information / Drafting / Recommendations / Workflow Assistance) and the explicit list of actions AI may never take. Do not build any AI feature that crosses that line, even if it seems convenient.
   - Section 24 (Implementation Phases) and Section 25 (Open Decisions Requiring Owner Sign-off) — Section 25 lists six decisions (AI hosting model, key-management product, DR targets, break-glass admin holder, CRM build-vs-integrate, warm-standby location) that are **not yet resolved**. Do not silently pick a default for any of these — flag it and ask, or stub the integration point clearly so it's swappable later.
   - Section 27 (Audit Traceability Matrix) — if you're ever unsure why a table, workflow state, or module exists, check here for the originating rationale.

2. `db/schema.sql` — the first-cut PostgreSQL schema, organized by domain schema (identity, organization, land, compliance, documents, design, quantities, budget, procurement, contracts, construction, quality, inventory, sales, customers, finance, workflow, communications, ai, audit, vendor_onboarding, reporting). It has been syntax-validated against the PostgreSQL grammar but not yet run against a live database or reviewed by the business owner. Treat it as a strong starting point, not gospel — you will need to add columns as each phase's module gets real requirements, and the `reporting` schema is intentionally empty (populated later via materialized views, see the comment at the bottom of the file).

## What to build first: Phase 0.5, then Phase 1

**Do not jump to Phase 1 feature code before Phase 0.5 is resolved.** Per Blueprint Section 24, Phase 0.5 is a two-week technology spike that must close three decisions before real implementation starts:

- AI hosting model (self-hosted open-weight model vs. commercial API under a zero-retention DPA) — Section 17.1.
- Event/queue technology (Postgres LISTEN/NOTIFY now, with NATS/Redis Streams as the stated upgrade path) — Section 7.1, Section 18.
- Reporting-store technology (logical-replication read replica vs. other) — Section 19.

If these haven't been decided yet, say so plainly and either wait for direction or propose the blueprint's stated defaults explicitly (don't bury the assumption).

**Phase 1 scope** (Blueprint Section 24): Identity, devices, legal entities, projects, audit, backups, owner console — plus the break-glass secondary admin credential mechanism (Section 3.2). Concretely, this means:

1. Stand up `db/schema.sql` against a local PostgreSQL 14+ instance (`identity`, `organization`, and `audit` schemas are the ones Phase 1 actually touches; the rest exist for later phases — don't build UI/API for them yet).
2. Passkey-based authentication with device binding and owner-approved device enrollment (Section 15).
3. Short-lived sessions with step-up authentication for the sensitive-action list in Section 15.
4. Legal entity and project CRUD, scoped by the `identity.user_roles` table (role × legal entity × project).
5. The audit event pipeline — every mutating action writes an `audit.audit_events` row via the hash-chain trigger already defined in the schema. Verify the chain is unbroken as part of your test suite, not just that rows get written.
6. Owner console with the break-glass secondary-admin flow (Section 3.2) — a sealed credential a second trusted party can invoke if the primary owner is unreachable, with the invocation itself logged as an audit event.
7. Backup wiring per Section 3.2 — at minimum, confirm the WAL-archiving and object-storage-sync jobs run and are observable; the full DR topology (warm standby, quarterly restore drill) is infrastructure work that can proceed in parallel but should be tracked, not skipped because it's "not code."

## Working conventions

- Follow Section 22 (Testing, CI/CD & Environment Strategy): define module API contracts before wiring modules together, write unit tests for business logic and integration tests for cross-module flows, and get CI running before Phase 1 is called done — not after.
- Every table in `db/schema.sql` that has `status` carries a `CHECK` constraint listing its valid values — treat that as the source of truth for state machines, and keep application-layer enums in sync with it rather than duplicating the list from memory.
- `audit.audit_events` is enforced append-only at the database level (triggers reject `UPDATE`/`DELETE`). Don't work around this from application code; if you think you need to, that's a sign the workflow design needs a compensating "correction" event instead, per Section 2's "No silent overwrites" principle.
- If a skill installed in this Claude account (`postgres-pro`, `security-reviewer`, `fastapi-expert`/`django-expert`/whichever backend framework gets chosen, `test-master`, `spec-miner`, etc.) is relevant to what you're building, use it — that's what they're there for.

## First deliverable

Before writing feature code, produce a short Phase 0.5 decision memo (even a stub, clearly marked "pending owner input" where you can't decide alone) and a Phase 1 module boundary doc listing the internal API contracts for Identity, Organization, and Audit. Then start on Identity.
