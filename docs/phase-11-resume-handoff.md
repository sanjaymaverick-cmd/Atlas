# Phase 11 Resume Handoff

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

The repository remains synthetic-data-only. `.claude/settings.local.json` is
intentionally untracked and untouched.
