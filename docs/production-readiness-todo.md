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
