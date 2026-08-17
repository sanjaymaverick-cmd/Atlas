# Atlas Cross-Tool Handoff — Phase 11 Checkpoint

Updated: 2026-08-17 (Asia/Calcutta)

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
- GitHub CLI authentication was invalid when publication was attempted. The
  branch has therefore not been pushed at this checkpoint and no PR was
  created. Re-authentication is required before publishing.

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

## Verified before suspension

- Ruff repository lint passed and 201 files passed format check.
- Import-linter: 25 contracts kept, 0 broken across 157 files.
- Alembic: `0012_phase11_ai_safety` is the sole head.
- Phase 11 adversarial service tests: 19 passed.
- Combined HTTP and AI safety tests: 55 passed.

## Pending gates and work

- Strict mypy was interrupted at the user's save/publish request after repeated
  mounted-drive WSL stalls; it is not recorded as passing for this checkpoint.
- Full pytest, Bandit, and pip-audit must be rerun after Phase 11 changes.
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
