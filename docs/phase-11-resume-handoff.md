# Atlas Cross-Tool Handoff — Phase 11 Checkpoint

Updated: 2026-08-18 (Asia/Calcutta)

This document is the authoritative resume point for another agentic coding
tool. Continue from the existing repository state. Do not rebuild or replace
the completed foundation.

## Repository state

- Repository: `sanjaymaverick-cmd/Atlas`
- Local checkout: `D:\work Dir\Atlas`
- Current branch: `phase-1-foundation`
- Phase 11 implementation commit: `6594110 Add Phase 11 AI safety foundation`
- The handoff itself is committed immediately after that implementation commit.
- Remote tracking state after committing this handoff: 15 commits ahead of
  `origin/phase-1-foundation`
- Remote `main` remains at the original Phase 0 commit `547bbe0`
- Worktree is clean except for intentionally untracked
  `.claude/settings.local.json`; preserve it and never stage or commit it.
- GitHub CLI authentication was invalid when publication was first attempted.
  It was valid again at the 2026-08-17 verification run (account
  `sanjaymaverick-cmd`, scopes `gist`, `read:org`, `repo`), so no interactive
  re-login was needed and the branch could be published.
- The GitHub repository `sanjaymaverick-cmd/Atlas` is currently **public**.
  The repository is synthetic-data-only, so nothing sensitive is exposed today,
  but the owner should confirm this is intended before any real business data,
  hosting configuration, or credential material is introduced.

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

- PostgreSQL integration coverage is now **verified**: 38 integration tests pass
  against a real PostgreSQL 16 instance, 0 skipped. This is the first time they
  have executed. Phases 1-10 were previously signed off without this coverage,
  so their database-backed behaviour is only now actually evidenced.
- Strict mypy is **not** clean: 6 pre-existing `fitz` errors remain (defect B).
  The one Phase 11-caused error was fixed.
- `alembic upgrade head` is **broken** on a clean database (defect C). The full
  test suite does not cover the migration path, so this is not caught by CI.
- Owner must approve self-hosted open-weight inference or a commercial provider
  under an executed enterprise zero-retention DPA before a real provider is
  implemented or Phase 11 is declared complete.
- After hosting sign-off: implement the selected provider, scoped retrieval,
  indirect-injection defenses, model evaluation/calibration, independent
  authority red-team, monitoring/kill switch, and final completion gates.

## Exact resume procedure

1. Inspect without modifying anything:

   ```powershell
   Set-Location 'D:\work Dir\Atlas'
   git status --short --branch --untracked-files=all
   git log -1 --oneline
   git diff --check
   ```

   Confirm that the history contains Phase 11 commit `6594110` followed by this
   handoff commit; the only untracked path should be
   `.claude/settings.local.json`.

2. Re-authenticate GitHub CLI interactively and verify the account:

   ```powershell
   gh auth login -h github.com
   gh auth status
   ```

   Never paste or record the token in source, logs, documentation, or chat.

3. Run the missing Phase 11 completion gates. Use the repository's existing
   Makefile/pyproject commands rather than inventing weaker alternatives:

   - strict mypy over the full configured source set;
   - complete pytest suite;
   - Bandit with zero medium/high findings and no unjustified suppressions;
   - pip-audit;
   - Ruff lint and format check;
   - import-linter;
   - Alembic single-head check.

   If `ATLAS_TEST_DATABASE_URL` is absent, report PostgreSQL integration tests
   as skipped, never as passed. Do not substitute a mock database for
   PostgreSQL-specific integration coverage. A disposable local PostgreSQL
   instance is appropriate when resources permit.

4. Fix only failures caused by the current branch. Keep changes reviewable,
   rerun affected checks, update this handoff and the production-readiness TODO,
   then commit explicitly scoped files. Never stage `.claude`.

5. Publish only after checking the diff and secret exposure:

   ```powershell
   git push -u origin phase-1-foundation
   ```

   Determine the repository's actual default branch, check for an existing PR,
   and create a draft PR only if none exists. Suggested title:
   `Build Atlas foundations through Phase 10 and add Phase 11 AI safety boundary`.
   The PR body must distinguish the fully verified Phase 10 baseline from the
   Phase 11 checks actually rerun, state that the inference provider remains
   disabled, mention skipped PostgreSQL tests explicitly, and confirm that no
   secrets or real data were added.

6. Do not implement a real AI provider until the owner makes and records the
   Blueprint section 25 hosting decision. Until then, Phase 11 remains a safe,
   fail-closed foundation rather than a completed production AI feature.

## Recommended next delivery order

1. Finish the pending Phase 11 verification gates.
2. Publish the branch and open/review the draft PR.
3. Obtain and document the owner-gated AI hosting decision.
4. Complete Phase 11 provider, retrieval, evaluation, monitoring, and
   red-team work under that approved decision.
5. Only after Phase 11 completion, proceed to the next blueprint phase.

## Publication handoff status

- Local commit created: yes (`6594110`).
- Local work saved: yes.
- Branch pushed: no; GitHub CLI token was invalid at the attempt.
- Pull request created: no; blocked by the same authentication failure.
- Uncommitted project changes after the handoff commit: none expected.
- Intentionally untracked user file: `.claude/settings.local.json`.

The repository remains synthetic-data-only. `.claude/settings.local.json` is
intentionally untracked and untouched.
