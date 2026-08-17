# Atlas — Private Real Estate Development ERP

Private, self-hosted operating platform for a multi-entity real estate
development group. See `docs/ERP_Technical_Blueprint_v2.docx` for the full
architecture and `db/schema.sql` for the PostgreSQL schema.

## Status

**Phase 1 in progress** — foundation layer built and tested.

Phase 0.5's spike decisions are recorded in `docs/phase-0.5-decision-memo.md`:
the event and reporting-store choices adopt the blueprint's stated defaults;
AI hosting remains open and gates Phase 11 only. None of the six Blueprint §25
owner decisions block Phase 1 — see the memo for how each is kept swappable.

Two of those decisions are worth starting now regardless, because their lead
time is not code: **who holds the break-glass credential** (§25 item 4 — they
need briefing and a physically sealed reference) and **the warm-standby
location** (§25 item 6 — the quarterly restore drill cannot start until the
site exists).

### Built

- Audit hash chain, corrected and verified against a live database — see
  `docs/schema-findings-phase1.md` for the two critical defects found
- Independent chain verifier (`atlas/platform/audit/chain.py`)
- §15 access-control check across all nine dimensions
- Step-up policy with a freshness window
- Break-glass state machine with a time-boxed grant
- Secrets/KMS pluggability boundary for the undecided §25 item 2
- CI pipeline: lint, mypy strict, module-boundary enforcement, unit and
  integration tests, coverage, bandit, pip-audit

### Next

Alembic baseline · WebAuthn passkey ceremony · session management ·
legal entity and project CRUD · owner console and CLI · backup wiring

## Repository layout

```
atlas/
  platform/       cross-cutting: db, secrets, kms, audit chain, access control
  modules/        identity, organization, audit
  owner_console/  admin API + CLI
db/schema.sql     canonical PostgreSQL DDL, all domains
docs/             blueprint, audit report, decision memo, module boundaries
tests/            integration tests (require a live PostgreSQL)
```

## Getting started

```bash
make install                       # venv + dependencies
make test-unit                     # no database needed
make check                         # everything CI runs
```

Integration tests need PostgreSQL 14+ and `ATLAS_TEST_DATABASE_URL`. See
`docs/local-postgres.md`, which includes a rootless setup for machines with
neither Docker nor sudo.

## Confidentiality

Strictly confidential. Do not make this repository public.
