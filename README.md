# Atlas — Private Real Estate Development ERP

Private, self-hosted operating platform for a multi-entity real estate development group. See `docs/ERP_Technical_Blueprint_v2.docx` for the full architecture and `db/schema.sql` for the first-cut PostgreSQL schema.

## Status

Phase 0 — pending owner sign-off on the open decisions listed in Blueprint v2 Section 25 (AI hosting model, key-management product, DR targets, break-glass admin holder, CRM build-vs-integrate, warm-standby location).

## Repository layout

```
docs/
  ERP_Technical_Blueprint_v2.docx     — build-ready architecture (supersedes v1.0)
  ERP_Independent_Architecture_Audit_Report.docx
  ERP_Planning_Transcript_and_Handoff.docx / .pdf
db/
  schema.sql                          — PostgreSQL DDL, all domains, Phase 0/1 foundation
CLAUDE_CODE_KICKOFF.md                — implementation kickoff prompt for Claude Code
```

## Getting started

1. Read `docs/ERP_Technical_Blueprint_v2.docx`, Sections 24–25, before writing any code.
2. Resolve the Phase 0.5 technology spike decisions before Phase 1 implementation begins.
3. Apply `db/schema.sql` to a local PostgreSQL 14+ instance to stand up the Phase 0/1 foundation.
4. Hand `CLAUDE_CODE_KICKOFF.md` to Claude Code to begin Phase 1 (Identity, devices, legal entities, projects, audit, backups, owner console).

## Confidentiality

Strictly confidential. Do not make this repository public.
