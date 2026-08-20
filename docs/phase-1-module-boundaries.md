# Phase 1 — Module Boundaries and Internal API Contracts

**Closes:** Blueprint §22 ("internal module API contracts defined before
implementation begins — each module exposes a documented interface; other
modules integrate against that interface, not against internal tables")

Phase 1 has three business modules — Identity, Organization, Audit — over a
shared platform layer. This document is what each publishes, what each keeps
private, and how the boundary is enforced.

## How the boundary is enforced

By `import-linter`, run in CI, not by convention. Each module publishes
`contracts.py` (its interface) and `schemas.py` (its DTOs). Everything else —
`models.py` (ORM mappings onto tables), `repository.py` (queries),
`webauthn_adapter.py` — is unreachable from outside the module, and a pull
request that reaches into one fails the build.

Five contracts are declared in `.importlinter`:

| Contract | What it prevents |
|---|---|
| Layered architecture | `platform` importing a business module; `modules` importing `owner_console` |
| Identity internals private | Anything outside Identity touching its models, repository or WebAuthn adapter |
| Organization internals private | Same, for Organization |
| Audit internals private | Same, for Audit |
| Identity independent | Identity depending on Organization or Audit, which would make the graph cyclic |

**Why a Python package boundary rather than internal REST/RPC.** Blueprint §7
commits to a modular monolith and the audit endorsed that choice. An internal
network hop between modules in the same process buys no independent
deployability and no independent scaling — only serialisation cost and a second
copy of every DTO. What §22 actually asks for is that modules integrate against
a documented interface, and a `Protocol` plus a lint rule delivers that with a
static guarantee an HTTP boundary would not give.

`api.py` in each module is a thin FastAPI adapter that translates HTTP to
contract calls and holds no business logic. If a module ever does need to become
a real network service, `service.py` ports over unchanged.

---

## Platform layer

Cross-cutting infrastructure. Holds no business logic and must never import a
business module.

| Component | Responsibility |
|---|---|
| `platform/db.py` | Async engine and session factory |
| `platform/secrets/` | `SecretsProvider` protocol + development implementation. The swap point for §25 item 2. |
| `platform/kms/` | `KeyManagementProvider` protocol + development implementation |
| `platform/audit/chain.py` | Hash computation and chain verification, implemented independently of the database |
| `platform/audit/writer.py` | Insert wrapper for `audit.audit_events`; the database computes hashes |
| `platform/step_up.py` | The §15 sensitive-action list and its freshness window |
| `platform/access_control.py` | The §15 request check: user × role × legal entity × project × module × classification × action × device trust × session risk |

`platform/audit/chain.py` is deliberately a *second* implementation of the hash
formula in `audit.compute_record_hash()`. A verifier that asked the database to
compute the hashes would prove only that the database agrees with itself, which
is exactly what an attacker who had rewritten the trigger would want. The two
are pinned against each other by fixed vectors generated from a live PostgreSQL.

---

## Identity

The base module. Owns authentication, devices, sessions, scoped roles, and the
break-glass credential.

**Publishes** (`identity/contracts.py`):

| Operation | Purpose |
|---|---|
| `check_scoped_role(user_id, permission_code, legal_entity_id, project_id)` | Yes/no authorisation answer |
| `get_user(user_id)` | Non-sensitive user summary |
| `require_step_up(session_id, action)` | Enforce §15 step-up for a sensitive action |
| `get_session(session_id)` | Session validity, device trust, step-up freshness |

**Keeps private:** `identity.users`, `roles`, `permissions`, `role_permissions`,
`user_roles`, `devices`, `sessions`, `break_glass_credentials`; the WebAuthn
ceremony adapter; password/credential material of every kind.

The important consequence is that **no other module ever reads
`identity.user_roles`**. Organization does not join against it to decide who may
edit a project; it asks `check_scoped_role` and receives a boolean. The scoping
rule — a role may be global, or bound to a legal entity, or to a project — stays
in one place, so §2's legal-entity separation and project isolation are enforced
once rather than re-implemented per module.

`break_glass.py` lives here as pure logic, tested without a database: the
`sealed → invoked → revoked` machine the database's CHECK constraint cannot
express, and the time-boxed grant that avoids promoting the holder to a
permanent owner.

The step-up *policy* deliberately does **not** live here. Its action list spans
contracts, payments, vendor masters and documents, so it belongs to no single
business module; it sits in `platform/step_up.py` where `access_control` can
reach it without the platform layer depending on Identity. Identity still owns
the step-up *ceremony* and the session row that records it.

## Organization

Legal entities and projects. Phase 1 scope only: `buildings`, `floors`,
`units`, `parties`, `vendors` and `contractors` exist in `schema.sql` for later
phases and get no models, service or router yet.

**Publishes:** `get_project`, `get_legal_entity`, `list_projects_for_user`,
and existence/scope checks other modules need to validate a `project_id` or
`legal_entity_id` without querying the tables directly.

**Depends on:** `identity.contracts` only.

Every mutation writes an `audit.audit_events` row and increments `version` in
the same transaction — Blueprint §2's "no silent overwrites" is a property of
the write path, not a convention.

## Audit

Read and verify. It does not own the write path: writes go through
`platform/audit/writer.py` so that a module recording an audit event does not
need to depend on the Audit module.

**Publishes:** `verify_chain()` (walks the chain and recomputes every hash) and
`export_for_owner_console()` (gated on owner identity and a fresh step-up —
`audit.export` is on the §15 sensitive list).

**Keeps private:** direct access to `audit.audit_events`.

There is no update or delete path, at any level. The table rejects both at the
database level, and a compensating "correction" event is the only way to record
that an earlier event was wrong — per §2, "no silent overwrites".

---

## Owner console

Not a module: an aggregation over the three, plus a Typer CLI that calls the
same services. Phase 1 delivers an admin API and CLI rather than a web UI —
no frontend framework has been chosen, and building browser UI ahead of a
tested passkey ceremony would be premature. The CLI exists so the owner can
approve devices and manage the break-glass credential from day one.

Everything here requires `is_owner` plus a fresh step-up, with one deliberate
exception: **break-glass invocation authorises on holder identity, not owner
status**. An emergency mechanism that required the owner's approval to use
would be useless in the emergency it exists for — the owner being unreachable
is the triggering condition.

---

## Dependency graph

```
owner_console
     |
     v
  modules:  organization ---> identity <--- audit
                  |              |            |
                  v              v            v
              platform (db, secrets, kms, audit, access_control)
```

Acyclic, with Identity as the base. Arrows are the only permitted direction,
and `import-linter` fails the build on any other.
