# Phase 2 — Documents module boundaries

The Documents module owns document metadata, immutable revisions, scan/review
state, controlled previews, and export approvals. It publishes only
`contracts.py` and `schemas.py`; ORM mappings, local storage, PDF rendering, and
workflow implementation remain private.

Documents depends on Identity's published contract for project-scoped
permissions. It does not query Identity or Organization tables and does not
import Organization or Audit internals. Audit writes use the platform writer so
every mutation remains in the caller's database transaction.

The HTTP layer may compose the concrete service and local adapter, but routers
call only `DocumentsContract`. Import-linter enforces both the privacy boundary
and Documents' independence from Organization and Audit.

Local binary storage is an adapter, not a business-record database. PostgreSQL
stores an opaque object key and lowercase SHA-256 digest. The local adapter is
append-only, rejects traversal/URLs/backslashes and symlinked roots, refuses
overwrite, limits object size, and verifies integrity on every read. Production
must replace it with encrypted object storage while preserving that contract.

Preview tokens are random and stored only as hashes. A preview is bound to the
originating user and session, expires after ten minutes, rechecks the scoped
permission, verifies the stored object, applies a session-bound watermark, and
returns a non-cacheable sandboxed PDF. The watermark uses UUIDs and UTC time,
not email, phone, IP address, or other direct personal data.

Exports use a four-eyes workflow. Only approved/issued revisions qualify; the
requester cannot approve their own request; request and download require a
fresh passkey step-up; approval expires after fifteen minutes; and a successful
integrity-checked download consumes the approval.
