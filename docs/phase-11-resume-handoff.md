# Atlas Handover — Phases 1-10 built, Phase 11 boundary in place

Updated: 2026-08-18 (Asia/Calcutta)

This document is the authoritative resume point for whoever picks the project up
next, human or agentic. Continue from the existing repository state; do not
rebuild or replace the completed foundation.

Read this section first if you read nothing else. Phases 1-10 are built and, as
of 2026-08-18, actually verified against a real database for the first time —
the integration suite had never run before, because `db/schema.sql` could not be
applied to an empty database. That is fixed. Phase 11 is a deliberately
fail-closed AI safety foundation with **no inference provider wired up**, and it
must stay that way until the owner records the Blueprint §25 hosting decision.

Three things are known-broken or undecided and are documented rather than
hidden: the Alembic migration chain cannot provision a database from empty,
strict mypy has 6 unresolved errors, and the `db/schema.sql` freeze rule has no
enforcement mechanism. See "Handover status" at the end for the ordered list.

## Repository state

- Repository: `sanjaymaverick-cmd/Atlas` (currently **public** — see below)
- Local checkout: `D:\work Dir\Atlas`
- Branch: `phase-1-foundation`, pushed and in sync with
  `origin/phase-1-foundation`. Nothing uncommitted, nothing unpushed.
- Remote `main` remains at the original Phase 0 commit `547bbe0`; the branch is
  26 commits ahead of it.
- Draft pull request: <https://github.com/sanjaymaverick-cmd/Atlas/pull/1>
  "Build Atlas foundations through Phase 10 and add Phase 11 AI safety boundary".
  Open, still a draft, not merged.

Commits on this branch, most recent first:

| Commit | What it did |
| --- | --- |
| `f036207` | Ratify the `db/schema.sql` freeze exception |
| `b990bdc` | Fix schema ordering so the integration suite can run |
| `2394628` | Rerun Phase 11 completion gates, record blocking defects |
| `71a791e` | Document Phase 11 cross-tool handoff |
| `6594110` | Add Phase 11 AI safety foundation |

- Worktree is clean except for intentionally untracked `.claude/`
  (`settings.local.json` and a Claude Code `RESUME.md` checkpoint). Both are
  covered by a global gitignore. Preserve them; never stage or commit them.
- GitHub CLI auth is valid (account `sanjaymaverick-cmd`). It was invalid at the
  original checkpoint, which is why publication was blocked then.
- The repository is **public**. It is synthetic-data-only, so nothing sensitive
  is exposed today, but confirm this is intended before any real business data,
  hosting configuration, or credential material is introduced. Recorded in
  `docs/production-readiness-todo.md`.

## Environment notes for whoever picks this up

The repository lives on a Windows drive under WSL. DrvFs per-file latency is
high enough that running the toolchain from `/mnt` looks like a hang rather than
slowness — this is what stalled strict mypy at the original checkpoint.

- Use the Linux-filesystem virtualenv at `~/.atlas-venv`, not `/mnt/.../.venv`.
  `make` targets accept `ATLAS_VENV=~/.atlas-venv`.
- PostgreSQL 16.15 is installed user-local via micromamba. Start it with:
  `pg_ctl -D ~/.local/atlas-pgdata -o "-p 55432 -k /tmp" -l /tmp/pg.log start`,
  and put `~/.local/micromamba/root/envs/atlaspg/bin` on `PATH` — the test
  fixture shells out to `psql`, so the suite errors without it.
- `ATLAS_TEST_DATABASE_URL="postgresql://atlas@/atlas_test?host=/tmp&port=55432"`.
  Integration tests skip silently when it is unset, which is exactly how the
  schema defect stayed hidden for eight phases. Always set it.
- `~/.atlas-venv` needed `pymupdf` installed separately; it was missing.

## Non-negotiable operating constraints

- Read `README.md`, `docs/ERP_Technical_Blueprint_v2.docx`,
  `docs/phase-0.5-decision-memo.md`, `docs/phase-1-module-boundaries.md`,
  `docs/schema-findings-phase1.md`, `db/schema.sql`,
  `CLAUDE_CODE_KICKOFF.md`, `pyproject.toml`, `Makefile`, and `.importlinter`
  before making architectural changes.
- Preserve all existing user work, especially untracked local settings.
- Never use `git reset --hard`, `git checkout --`, destructive cleanup, or
  force-push.
- Use synthetic fixtures only. Do not add credentials, secrets, production
  URLs, personal information, or real business data.
- `db/schema.sql` is canonical DDL. Never use ORM `create_all` or let ORM
  metadata redefine the database.
- Preserve modular-monolith dependency direction and import-linter contracts.
- Every mutation must write its audit event in the same transaction.
- Preserve optimistic versioning, before/after audit state, and archival in
  place of business-record deletion.
- Do not silently resolve any open Blueprint section 25 decision.
- Record every security, secrets, privacy, integrity, hosting, and
  production-readiness decision in `docs/production-readiness-todo.md` for
  owner review before go-live.
- Complete and verify one phase before starting the next.

## Current boundary

Phase 11 hosting remains an open Blueprint §25 owner decision. No model vendor,
endpoint, runtime, weights, API key, or external data transfer has been selected.
The default inference provider fails closed with `hosting_not_configured`.

## Implemented checkpoint

- Privacy-minimized canonical AI DDL and migration `0012_phase11_ai_safety`.
- Raw prompts, responses, recommendations, and free-form authority reasons were
  replaced by digests, lengths, scope IDs, confidence, controlled-document IDs,
  and enumerated action/reason codes.
- Four-level intent/authority mapping and permanent forbidden-effect policy.
- Deterministic prompt-injection refusal signals and non-overridable system/data
  separation in the provider prompt contract.
- Configurable confidence refusal with a provisional `0.80` threshold.
- Disabled, swappable inference provider contract; no real inference backend.
- Thin authenticated HTTP evaluation endpoint that rejects provider secrets,
  raw document text, and unknown fields.
- Same-transaction minimized audit event for every evaluated or blocked query.
- Import-linter boundaries, README guidance, and Phase 11 owner TODO decisions.

## Verification runs of 2026-08-17 / 2026-08-18 (completion gates)

All gates were rerun from a virtualenv on the Linux filesystem (`~/.atlas-venv`)
rather than the `/mnt` drive. That removes the DrvFs latency that stalled the
previous strict-mypy attempt; mypy now completes in well under a minute.

PostgreSQL was real, not mocked: a local PostgreSQL 16.15 cluster (micromamba,
port 55432, socket `/tmp`) with disposable databases recreated per run.

| Gate | Result |
| --- | --- |
| Ruff lint | passed |
| Ruff format check | 202 files already formatted |
| Import-linter | 25 contracts kept, 0 broken (157 files) |
| Alembic heads | `0012_phase11_ai_safety` is the sole head |
| Bandit (`-ll`) | 0 medium, 0 high, 0 `nosec` suppressions, 0 skipped tests |
| pip-audit | no known vulnerabilities (only the local `atlas` package skipped) |
| Strict mypy | **6 pre-existing errors remain** — defect B below |
| pytest — unit | 278 passed |
| pytest — PostgreSQL integration | **38 passed, 0 skipped, 0 errored** |
| pytest — full suite | **316 passed** |
| Phase 11 AI safety + HTTP tests | 55 passed |
| `alembic upgrade 0001_baseline` | applies cleanly, 89 tables |
| `alembic upgrade head` | **fails at 0002** — defect C below |

The 38 PostgreSQL integration tests pass for the first time in the project's
history. Before the schema fix below they had never executed at all.

### Fixed in these runs

1. **`db/schema.sql` now applies to a clean database.** The `documents` section
   was relocated to sit after `organization` and before `land`, because
   `land.due_diligence_items` references `documents.documents(id)`. The move is
   a pure relocation: the sorted contents of the file before and after are
   byte-identical, so no statement was added, removed, or altered and the
   resulting database is the same set of objects in a different creation order.
   Hoisting `CREATE SCHEMA documents` alone was tried first and is *not*
   sufficient — the apply then fails on the missing table.

   This also repairs migration `0001_baseline`, which executes `db/schema.sql`
   verbatim. `alembic upgrade 0001_baseline` against an empty database now
   succeeds and creates 89 tables; previously it could not run at all.

   Note on the freeze rule: `0001_baseline` declares `db/schema.sql` frozen from
   that revision onward. This edit is a deliberate, narrow exception — the file
   as committed could not be applied by any path, and the change is provably
   content-identical, so no already-provisioned database diverges.
   **Ratified by the repository owner on 2026-08-18**, for this specific
   reordering only; it is not standing permission to edit the file. How the
   freeze is *enforced* remains open — see `docs/production-readiness-todo.md`.

2. **`trust_level` in `tests/integration/test_session_token_auth.py`** inserted
   `'trusted'`, which the canonical DDL has never permitted — the CHECK allows
   `'standard'`/`'elevated'` and `DeviceTrust` mirrors exactly those. Every
   sibling integration test already used `'standard'`. Wrong since Phase 1
   (`92d0478`) and invisible because the test never ran.

3. **`test_valid_token_authenticates_and_plain_token_is_not_stored`** asserted
   with `scalar_one()` over the whole of `identity.sessions`, which silently
   assumed it was the only test ever to write a session row. True in isolation,
   false in a full-suite run. The assertion is now scoped to the row the test
   seeds, which preserves its meaning (the stored value is the hash, and the
   plain token is not stored anywhere).

4. **`atlas/api/tests/test_api.py:721`** carried a `# type: ignore[arg-type]` on
   `assistant_service=assistant or FakeAssistant()` that strict mypy reported as
   unused. `FakeAssistant` satisfies the parameter type, so it was removed. This
   was the only mypy error Phase 11 introduced.

### Defects still open — pre-existing, not fixed

**B. Strict mypy cannot resolve `import fitz` (6 errors in 3 files).**
`atlas/modules/documents/preview.py` and two documents test modules import the
deprecated PyMuPDF alias with `# type: ignore[import-untyped]`. PyMuPDF 1.28.2
ships `fitz` without a `py.typed` marker, so mypy reports `import-not-found` and
also flags the existing suppression as unused. Runtime still works but warns,
and upstream has announced removal of the alias. Root cause is the unpinned
`pymupdf>=1.24`. Fix is to import `pymupdf` (which does carry `py.typed`) and
pin a reviewed version — a documents-module change needing its own review, and
one that pairs with the existing Phase 2 renderer-sandboxing item.

**C. `alembic upgrade head` fails on a clean database at `0002`.**
`0001_baseline` applies `db/schema.sql`, which already contains
`identity.webauthn_challenges` — it was added to the file by commit `4e4c85d`
("Complete WebAuthn and local Phase 2 documents") *after* `0001` declared the
file frozen. `0002_webauthn_challenges` then creates the same table again and
fails with `relation "webauthn_challenges" already exists`.

Consequence: the migration path — the documented way to provision a database —
cannot build one from empty. This was masked because the integration fixture
applies `db/schema.sql` directly and never exercises the migration chain, so
the full test suite passes while `alembic upgrade head` is broken. Discovered
2026-08-18 while sanity-checking the schema change above; not caused by it.

Resolving it is an owner decision: either drop `webauthn_challenges` from
`db/schema.sql` so `0002` owns it, or make `0002` a no-op against a baseline
that already has the table, or re-baseline the chain. Whichever is chosen, add
a CI check that runs `alembic upgrade head` against an empty database, since
nothing currently tests that path.

## Pending gates and work

The ordered, actionable list lives under "Handover status" at the end of this
document — this section records only the current gate status, so the two do not
drift apart.

- PostgreSQL integration coverage is now **verified**: 38 integration tests pass
  against a real PostgreSQL 16 instance, 0 skipped. First time they have ever
  executed, so the Phase 1-10 database-backed behaviour is only now evidenced.
- Strict mypy is **not** clean: 6 pre-existing `fitz` errors (defect B).
- `alembic upgrade head` is **broken** on a clean database (defect C), and the
  test suite does not cover the migration path, so CI does not catch it.
- Everything else passes: Ruff, import-linter, Alembic single-head, Bandit,
  pip-audit, and the full 316-test suite.
- Phase 11 cannot be declared complete until the owner records the Blueprint §25
  hosting decision, and the provider, scoped retrieval, indirect-injection
  defenses, evaluation and calibration, monitoring and kill switch, and the
  independent authority red-team are built under it.

## Resume procedure

Steps 1-5 of the original procedure (inspect, re-authenticate, run the missing
gates, fix branch-caused failures, publish) are **done**. The branch is pushed
and PR #1 is open. What follows is what a new session should actually do.

1. Bring the environment up — see "Environment notes" above. Start PostgreSQL,
   put `psql` on `PATH`, export `ATLAS_TEST_DATABASE_URL`, and use
   `~/.atlas-venv`. Confirm the baseline before changing anything:

   ```bash
   git status --short --branch --untracked-files=all   # expect clean
   ~/.atlas-venv/bin/python -m pytest -q               # expect 316 passed
   ```

   If the integration tests report as skipped rather than passed, the database
   is not wired up — fix that before trusting any result.

2. Take the open items in the order listed under "Handover status" below. Item 1
   (`alembic upgrade head`) is a real breakage in the documented provisioning
   path and should go first.

3. Keep changes scoped and reviewable, rerun the affected gates, update this
   document and `docs/production-readiness-todo.md`, then commit explicitly
   named files. Never stage `.claude`.

4. Do not implement a real AI provider until the Blueprint §25 hosting decision
   is made and recorded. Until then Phase 11 stays a fail-closed foundation.

## Recommended next delivery order

1. Repair the migration chain so `alembic upgrade head` builds a database from
   empty, and add CI coverage for that path — nothing currently tests it.
2. Resolve the PyMuPDF import and pin, so strict mypy is clean.
3. Decide how the `db/schema.sql` freeze is enforced.
4. Re-record the Phase 1-10 sign-offs against the now-passing integration suite.
5. Obtain and document the owner-gated AI hosting decision.
6. Only then build the Phase 11 provider, scoped retrieval, indirect-injection
   defenses, evaluation and calibration, monitoring and kill switch, and the
   independent authority red-team under it.
7. Only after Phase 11 is genuinely complete, move to the next blueprint phase.

## Handover status — 2026-08-18

- All local work is committed and pushed. Working tree clean.
- Branch published; draft PR #1 open and up to date with the current state.
- Untracked by design and left untouched: `.claude/settings.local.json`,
  `.claude/RESUME.md`.
- No secrets, credentials, production URLs, personal information, or real
  business data were added at any point. The repository remains
  synthetic-fixtures-only, and diffs were scanned for credential patterns
  before each push.

### What is genuinely verified now

316 tests pass — 278 unit and 38 PostgreSQL integration — against a real
PostgreSQL 16 instance with the database recreated per run, 0 skipped. Ruff,
import-linter (25 contracts), Alembic single-head, Bandit (0 medium, 0 high, 0
suppressions) and pip-audit all pass.

The integration tests had never executed before this work. Treat the Phase 1-10
sign-offs accordingly: the behaviour is evidenced now, but it was not when those
phases were declared complete.

### Open items, in the order they should be taken

1. **`alembic upgrade head` is broken** on a clean database at `0002`
   (defect C above). The migration path cannot provision a database from empty,
   and CI does not cover it. Highest priority: it is a real breakage in the
   documented deployment path, not a policy question.
2. **Strict mypy is not clean** — 6 pre-existing `fitz` errors (defect B).
   Needs a decision on pinning PyMuPDF and moving to the `pymupdf` import.
3. **Freeze enforcement for `db/schema.sql`** is still open. The exception in
   `b990bdc` is ratified, but the rule has no mechanism behind it and has
   already been breached once unnoticed — which is what caused item 1.
4. **Re-record the Phase 1-10 sign-offs** on the basis of the now-passing
   integration coverage.
5. **The Blueprint §25 AI hosting decision** — owner-gated, and the gate on
   everything else in Phase 11.

### Do not do

- Do not implement a real inference provider before item 5 is decided and
  recorded. Phase 11 is a fail-closed safety foundation, not a working AI
  feature, and must not drift past that boundary.
- Do not declare Phase 11 complete while items 1-3 are open.
- Do not merge PR #1 without a decision on items 1 and 2 — the branch carries
  two known-failing gates, both documented rather than hidden.
