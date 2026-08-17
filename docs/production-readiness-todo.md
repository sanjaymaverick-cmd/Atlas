# Production-readiness decisions and TODOs

This register records provisional choices made while Atlas is built locally.
Every item must be reviewed, replaced where necessary, and explicitly signed
off before production data or users are introduced.

## Global security and infrastructure

- [ ] Select and configure the production secrets manager and KMS/HSM. Local
  environment-variable providers are development-only and must remain unable
  to start in production mode.
- [ ] Replace every synthetic/local database URL, relying-party origin, host,
  certificate, and object-storage endpoint with secret-managed production
  configuration. Never commit the resulting values.
- [ ] Confirm the WebAuthn RP ID and exact HTTPS origins; perform real-device
  UAT and document supported browser/authenticator combinations.
- [ ] Confirm RTO/RPO, warm-standby location, backup retention, key custodians,
  and quarterly restore-drill ownership.
- [ ] Name the break-glass credential holder and incident commander; seal and
  test the recovery procedure without recording credential material here.
- [ ] Configure WAF, rate limiting, private network access, TLS policy, security
  headers, log redaction, monitoring, alert routing, vulnerability scanning,
  dependency updates, and incident-response notification obligations.
- [ ] Review data classification, retention, legal holds, archival, privacy
  notices, data-subject procedures, and jurisdiction-specific compliance with
  qualified legal/security advisers.
- [ ] Run a production threat-model review, penetration test, access-control
  review, audit-chain verification, restore drill, and secrets scan before
  launch.

## Phase 2 — Documents

- [ ] Select the encrypted object-storage implementation and customer-managed
  key configuration. Opaque object keys are stored in PostgreSQL; filesystem
  paths, public URLs, credentials, and encryption keys are forbidden.
- [ ] Replace `LocalDocumentStorage` before production. Its append-only,
  traversal-resistant, size-limited and SHA-256-verifying behavior is the
  minimum contract the encrypted object-store adapter must preserve.
- [ ] Define permitted upload MIME types, maximum sizes, archive handling, and
  the production malware-scanning engine. Files must remain quarantined until
  scanning succeeds.
- [ ] Define the authoritative SHA-256 calculation point and verify content on
  ingest and retrieval. A revision's binary and checksum are immutable.
- [ ] Review the provisional database invariants: every document must belong to
  a project, revision codes are unique per document, object keys are globally
  unique, and checksums are lowercase SHA-256 values.
- [ ] Approve classification-to-access and retention rules for public,
  internal, confidential, and restricted documents.
- [ ] Review the provisional device rule: restricted document content requires
  an owner-elevated device; all authenticated requests reject session risk
  scores above the platform threshold of 50.
- [ ] Approve dynamic-watermark content and privacy treatment. The provisional
  design will use user ID, session ID, and UTC timestamp—not email, phone, IP,
  or other personal information—unless explicitly approved.
- [ ] Define export-approval thresholds, approver roles, expiry, download
  limits, and whether restricted documents may ever be exported.
- [ ] Review the provisional four-eyes rules: requester and approver must differ,
  approval expires after 15 minutes, downloads require fresh step-up, and each
  approval permits exactly one integrity-checked download.
- [ ] Add an orphan-object reconciliation job. A local object can remain
  unreferenced if filesystem storage succeeds but the database transaction is
  later rolled back; it must be reported and retained until an approved cleanup
  policy exists.
- [ ] Select preview/PDF conversion tooling and sandbox it with no outbound
  network, read-only inputs, resource limits, and disposable working storage.
- [ ] Security-review and sandbox the provisional PyMuPDF preview renderer;
  pin the approved version, fuzz malformed PDFs, cap pages/dimensions/runtime,
  and run conversion in an isolated worker before production use.

## Later phases

- [ ] Add phase-specific decisions here before each phase is declared complete.
- [ ] CRM build-versus-integrate and provider choice remain open until Phase 8.
- [ ] AI hosting, zero-retention DPA or self-hosting, prompt-injection controls,
  confidence thresholds, and authority-boundary red-team remain mandatory
  gates before Phase 11.

## Phase 4 — Budgets, procurement, contracts, and vendor onboarding

- [ ] Approve budget and purchase-order approval thresholds, segregation of
  duties, delegated authority, amendment rules, and four-eyes requirements.
- [ ] Define vendor activation/suspension ownership and verify that no purchase
  order can be issued until onboarding is active and required compliance
  evidence is current.
- [ ] Classify PAN, GST, bank verification, labour registrations, insurance
  policies, contacts, and KYC evidence. Approve masking, retention, access,
  export, breach-notification, and data-subject procedures with legal/privacy
  advisers.
- [ ] Raw KYC, bank proof, cheque images, signatures, credentials, and account
  numbers must never appear in operational fields, logs, fixtures, or audit
  payloads. Store evidence as restricted Documents records with controlled
  preview/export; migrate and remove the provisional `object_storage_key` field
  before production.
- [ ] Select an e-signature provider and approve identity assurance, webhook
  signature verification, replay protection, evidence retention, data
  residency, and provider-failure/manual fallback procedures.
- [ ] Approve contract/PO cancellation, supersession, dispute, payment, and
  expiry workflows. Confirm whether issued financial commitments require fresh
  passkey step-up and independent approval.
- [ ] Review provisional invariants: one onboarding record per vendor,
  non-negative monetary/quantity fields, immutable executed-document evidence,
  and archival instead of deletion.

## Phase 5 — Construction, site diary, QA/QC, snagging, and EHS

- [ ] Approve the offline site-diary conflict policy. The provisional design
  uses a client-generated UUID for idempotency, accepts one diary per project
  and calendar date, preserves server versions, and rejects conflicting edits
  rather than silently selecting a winner.
- [ ] Select the approved mobile-device storage and sync design: encrypted
  local database, device binding, remote wipe/revocation behavior, minimum OS,
  TLS pinning decision, retry limits, clock-skew handling, and maximum offline
  retention must be security-reviewed before real field data is cached.
- [ ] Classify visitor logs, worker counts, incident narratives, assignees,
  photos, location/unit references, and device timestamps. Define minimization,
  notice/consent, retention, access, export, and incident-reporting rules.
- [ ] EHS fatality/major-incident handling requires jurisdiction-specific
  escalation, regulator notification, legal hold, investigation ownership, and
  tamper-evident evidence procedures approved by qualified advisers.
- [ ] Approve inspection template governance, required evidence types,
  inspector independence, failed-inspection/NCR escalation, snag severity/SLA,
  rectification verification, and close authority.
- [ ] Site photos, certificates, inspection reports, and progress evidence must
  use restricted Documents records. Raw binaries, public URLs, GPS metadata,
  biometric data, and personal identifiers must not be embedded in JSON fields,
  logs, fixtures, or audit payloads.
- [ ] Review provisional progress invariants: percentage is 0–100, one update
  per activity/date, schedule dates cannot run backwards, and progress evidence
  remains immutable after submission.
- [ ] Choose the authoritative project/site business timezone and date rollover
  policy. The local service currently derives automatic transition dates from
  UTC; do not assume UTC calendar dates match the legally relevant site date.

## Phase 3 — Land, legal, financing, and compliance

- [ ] Approve the due-diligence checklist taxonomy, mandatory categories,
  waiver authority, and evidence-retention rules with qualified legal counsel.
- [ ] Review which land, title, lender, RERA, PDC, and statutory records contain
  personal or regulated financial data; restrict fields, exports, logs, and
  retention accordingly.
- [ ] Confirm that lender names and reference numbers are operational metadata
  only. Bank account numbers, cheque images, credentials, and payment secrets
  must remain in classified document storage or the accounting system of record.
- [ ] Approve loan-default, bounced-PDC, overdue-obligation, approval-expiry,
  and RERA-lapse escalation thresholds and notification recipients.
- [ ] Review the provisional invariant that each loan has at most one EMI/PDC
  installment of a given type per due date; revise if business practice permits
  split instruments.
