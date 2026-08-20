# Phase 0.5 — Technology Spike Decision Memo

**Status:** two of three spike decisions closed; one requires owner input and
does not block Phase 1.
**Date:** 17 August 2026
**Closes:** Blueprint §24 (Phase 0.5), §7.1, §17.1, §18, §19

Blueprint §24 inserts a two-week technology spike before Phase 1 code is
written, to close three decisions. This memo records where each stands. Where
the blueprint already states a default, that default is adopted explicitly
rather than re-litigated. Where no default exists, the decision is left open
and marked — not quietly resolved.

---

## 1. Event / queue technology — **CLOSED, blueprint default adopted**

**Decision:** PostgreSQL `LISTEN`/`NOTIFY` for workflow-state-change events.

The mechanism already exists in `db/schema.sql`:
`workflow.publish_state_change_event()` fires on every
`workflow.workflow_instances` update, writes a
`communications.notification_events` row and issues `pg_notify`.

**Rationale (Blueprint §7.1, §18):** appropriate at current single-server,
single-region scale, and it avoids standing up a broker before the load exists
to justify one. Downstream consumers — in-app notification, email/SMS
reminders, audit, reporting refresh — subscribe rather than being called
directly by the originating module, which is what removes the tight coupling
the audit flagged.

**Upgrade path, on record:** a dedicated broker (NATS or Redis Streams) once
the group operates across multiple cities or transaction volume grows past what
§6 anticipates. The trigger already writes a durable `notification_events` row,
so a broker can be introduced as a new consumer of that table without
rewriting publishers.

## 2. Reporting-store technology — **CLOSED, blueprint default adopted**

**Decision:** a logical-replication read replica of the primary PostgreSQL,
with the `reporting` schema populated by materialised views.

**Rationale (Blueprint §19):** keeps CEO-dashboard and analytical queries off
the transactional primary without introducing a second database technology into
a self-hosted, single-operator footprint.

**Implementation deliberately deferred.** The `reporting` schema stays empty
until Phase 4+ has data worth aggregating, exactly as the comment at the foot of
`schema.sql` describes. The *decision* is closed now so it does not get
reopened at Phase 10 under delivery pressure.

## 3. AI hosting model — **OPEN. Requires owner sign-off.**

**Not decided, and deliberately not defaulted.**

Blueprint §17.1 is explicit that using a commercial API without an enterprise
zero-retention Data Processing Agreement contradicts the platform's "private by
default" principle, and treats this as a blocking decision rather than
something to be settled by whichever option is convenient. The two candidates
remain self-hosting an open-weight model, or a commercial API under a
zero-retention DPA.

**This does not block Phase 1.** The AI assistant is Phase 11. No `atlas/ai`
package exists, and the `ai` schema in `schema.sql` is unused. The decision is
needed before Phase 11 *design* begins, together with the prompt-injection
defences and the Level 1–4 authority red-team that §17.1 also gates that phase
on.

---

## Decisions taken outside the spike's three questions

### Backend stack — **DECIDED** (not a §25 item; ours to make)

Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · `py_webauthn` ·
opaque server-side session tokens.

- **Modular monolith** (§7) maps cleanly onto FastAPI routers plus dependency
  injection, with one deployable and one connection pool.
- **Database-first.** `db/schema.sql` is the canonical DDL; SQLAlchemy models
  are hand-written mappings onto it and never generate it. The schema's
  behaviour lives in triggers and CHECK constraints, and an ORM that believed
  it owned the schema would fight all of it.
- **Opaque session tokens, not JWT.** `identity.sessions` already carries
  `session_token_hash`, `revoked_at` and `risk_score` — a server-side
  revocable session. JWTs are stateless by design and would need a blocklist to
  support revocation, which is the session table again with extra steps.

### Background job queue — **NOT NEEDED YET, and not silently chosen**

Distinct from the event-bus decision above, and the blueprint states no default
for it. Phase 1 has no asynchronous job workload: notification delivery and
document processing arrive in Phase 2. Revisit then; likely candidates are
RQ or Dramatiq over Redis, but that is a proposal for Phase 2, not a decision
taken now.

---

## Open owner decisions (Blueprint §25) and their effect on Phase 1

| # | Decision | Blocks Phase 1? | How Phase 1 avoids being blocked |
|---|---|---|---|
| 1 | AI hosting model | No | Phase 11 concern; no AI code exists |
| 2 | Key-management product | No | `atlas/platform/secrets/` and `kms/` are protocols with a development-only implementation that refuses to run outside development. Swapping backends is one class plus one wiring line. |
| 3 | DR targets (RTO 4h / RPO 15m–24h) | No | Infrastructure. The 4-hour recommendation is already used as the break-glass grant TTL, so confirming or revising it changes one constant. |
| 4 | Break-glass holder | No | The mechanism is keyed only on `holder_user_id`. Who that is, is data. |
| 5 | CRM build vs. integrate | No | Phase 8 concern |
| 6 | Warm-standby location | No | Infrastructure |

**Net effect: none of the six blocks Phase 1**, provided the key-management and
break-glass pieces stay pluggable rather than hardcoded — which is how they are
built.

Two of these deserve prompting rather than waiting, because they have long lead
times that are not code: **#4** (the holder needs to be briefed and the
credential physically sealed before the mechanism is real) and **#6** (a second
physical site takes time to arrange, and the quarterly restore drill in §3.2
cannot start until it exists).

---

## A note on the staging environment

Blueprint §22 requires a staging/UAT environment before Phase 1 implementation
starts. Naming a cloud provider for it would silently decide §25 item 6, so it
is not named here. The working answer is the same PostgreSQL and application
stack deployed to a persistent host; which host is the owner's call, and is
tracked with the warm-standby decision rather than settled by default.
