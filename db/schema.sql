-- =====================================================================
-- Atlas ERP — PostgreSQL Schema v1.0
-- Private Real Estate Development ERP
-- Derived from: Technical Blueprint v2.0 (Sections 5 and 6)
-- Status: First-cut, build-ready schema for Phase 0/0.5 review and
--         Phase 1 implementation start. Expect column additions as
--         each phase's module is implemented — this is a foundation,
--         not a final migration.
-- Conventions: every business table carries id (UUID), legal_entity_id
--   and/or project_id where applicable, status, created_at/updated_at,
--   created_by/updated_by, version, archived_at. updated_at is kept
--   current automatically by a trigger installed at the bottom of this
--   file, so it is not repeated per table.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()

CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- SCHEMA: identity   (Blueprint §4, §15 Security Model, §3.2 DR)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS identity;

CREATE TABLE identity.users (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_group_id UUID,
  full_name         TEXT NOT NULL,
  email             TEXT NOT NULL UNIQUE,
  phone             TEXT,
  is_owner          BOOLEAN NOT NULL DEFAULT false,
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','deactivated')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID,
  updated_by        UUID,
  version           INT NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ
);

CREATE TABLE identity.roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE identity.permissions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code        TEXT NOT NULL UNIQUE,   -- e.g. 'contract.approve', 'payment.release'
  description TEXT
);

CREATE TABLE identity.role_permissions (
  role_id       UUID NOT NULL REFERENCES identity.roles(id),
  permission_id UUID NOT NULL REFERENCES identity.permissions(id),
  PRIMARY KEY (role_id, permission_id)
);

-- Scoped role assignment: a user's role can be limited to a legal entity and/or project.
CREATE TABLE identity.user_roles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES identity.users(id),
  role_id         UUID NOT NULL REFERENCES identity.roles(id),
  legal_entity_id UUID,
  project_id      UUID,
  granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  granted_by      UUID REFERENCES identity.users(id)
);

-- Passkey-bound devices (Blueprint §15: passkeys, registered devices, device trust)
CREATE TABLE identity.devices (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES identity.users(id),
  device_name         TEXT,
  passkey_credential_id TEXT NOT NULL UNIQUE,
  public_key          TEXT NOT NULL,
  -- WebAuthn signature counter. Must increase on every assertion; a counter
  -- that stalls or goes backwards indicates a cloned authenticator.
  sign_counter        BIGINT NOT NULL DEFAULT 0,
  trust_level         TEXT NOT NULL DEFAULT 'standard' CHECK (trust_level IN ('standard','elevated')),
  status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('pending_approval','active','revoked')),
  enrolled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  enrolled_by         UUID REFERENCES identity.users(id),  -- owner-approved enrollment
  last_used_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE identity.sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES identity.users(id),
  device_id        UUID NOT NULL REFERENCES identity.devices(id),
  session_token_hash TEXT NOT NULL,
  risk_score       NUMERIC(5,2) DEFAULT 0,
  step_up_verified BOOLEAN NOT NULL DEFAULT false,
  -- When step-up was last satisfied. Without this the boolean above never
  -- decays, so one step-up would silently authorise every later sensitive
  -- action for the life of the session. Freshness policy lives in
  -- atlas/modules/identity/step_up.py.
  step_up_verified_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at       TIMESTAMPTZ NOT NULL,
  revoked_at       TIMESTAMPTZ
);

-- One-time server-side WebAuthn ceremony state. Challenges are short-lived,
-- consumed under a row lock, and contain no credential or session secret.
CREATE TABLE identity.webauthn_challenges (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES identity.users(id),
  ceremony_type   TEXT NOT NULL CHECK (ceremony_type IN ('registration','authentication')),
  challenge       TEXT NOT NULL,
  expires_at      TIMESTAMPTZ NOT NULL,
  used_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_webauthn_challenges_expires
  ON identity.webauthn_challenges(expires_at)
  WHERE used_at IS NULL;

-- Blueprint §3.2: break-glass secondary admin for the single-owner-console risk.
CREATE TABLE identity.break_glass_credentials (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  holder_user_id   UUID NOT NULL REFERENCES identity.users(id),
  purpose          TEXT NOT NULL DEFAULT 'owner console succession',
  sealed_reference TEXT NOT NULL,  -- pointer to physically-secured credential, not the credential itself
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_invoked_at  TIMESTAMPTZ,
  status           TEXT NOT NULL DEFAULT 'sealed' CHECK (status IN ('sealed','invoked','revoked'))
);

CREATE INDEX idx_devices_user ON identity.devices(user_id);
CREATE INDEX idx_sessions_user ON identity.sessions(user_id);

-- =====================================================================
-- SCHEMA: organization   (Blueprint §4, §5)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS organization;

CREATE TABLE organization.business_groups (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by  UUID REFERENCES identity.users(id),
  updated_by  UUID REFERENCES identity.users(id),
  version     INT NOT NULL DEFAULT 1,
  archived_at TIMESTAMPTZ
);

CREATE TABLE organization.legal_entities (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_group_id  UUID NOT NULL REFERENCES organization.business_groups(id),
  name               TEXT NOT NULL,
  registration_number TEXT,
  entity_type        TEXT,   -- e.g. Pvt Ltd, LLP, Partnership
  status             TEXT NOT NULL DEFAULT 'active',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by         UUID REFERENCES identity.users(id),
  updated_by         UUID REFERENCES identity.users(id),
  version            INT NOT NULL DEFAULT 1,
  archived_at        TIMESTAMPTZ
);

CREATE TABLE organization.projects (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id          UUID NOT NULL REFERENCES organization.legal_entities(id),
  name                     TEXT NOT NULL,
  code                     TEXT NOT NULL UNIQUE,
  city                     TEXT,
  status                   TEXT NOT NULL DEFAULT 'planning',
  start_date               DATE,
  target_completion_date   DATE,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by               UUID REFERENCES identity.users(id),
  updated_by               UUID REFERENCES identity.users(id),
  version                  INT NOT NULL DEFAULT 1,
  archived_at              TIMESTAMPTZ
);

CREATE TABLE organization.buildings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES organization.projects(id),
  name        TEXT NOT NULL,
  code        TEXT,
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE organization.floors (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id  UUID NOT NULL REFERENCES organization.buildings(id),
  floor_number INT NOT NULL,
  name         TEXT,
  status       TEXT NOT NULL DEFAULT 'active',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE organization.units (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  floor_id     UUID NOT NULL REFERENCES organization.floors(id),
  unit_number  TEXT NOT NULL,
  unit_type    TEXT,           -- e.g. 2BHK, shop, parking
  carpet_area  NUMERIC(10,2),
  status       TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','booked','sold','possessed','blocked')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Base party record; Vendor / Contractor / Customer specialize this.
CREATE TABLE organization.parties (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  party_type      TEXT NOT NULL CHECK (party_type IN ('vendor','contractor','customer','other')),
  legal_name      TEXT NOT NULL,
  primary_contact TEXT,
  email           TEXT,
  phone           TEXT,
  gst_number      TEXT,
  pan_number      TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INT NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ
);

CREATE TABLE organization.vendors (
  id           UUID PRIMARY KEY REFERENCES organization.parties(id),
  category     TEXT,     -- e.g. materials, services
  status       TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','onboarding','active','suspended')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE organization.contractors (
  id             UUID PRIMARY KEY REFERENCES organization.parties(id),
  specialization TEXT,
  license_number TEXT,
  status         TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','onboarding','active','suspended')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_legal_entity ON organization.projects(legal_entity_id);
CREATE INDEX idx_buildings_project ON organization.buildings(project_id);
CREATE INDEX idx_floors_building ON organization.floors(building_id);
CREATE INDEX idx_units_floor ON organization.units(floor_id);
CREATE INDEX idx_units_status ON organization.units(status);

-- =====================================================================
-- SCHEMA: land   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS land;

CREATE TABLE land.land_parcels (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id   UUID NOT NULL REFERENCES organization.legal_entities(id),
  project_id        UUID REFERENCES organization.projects(id),
  survey_number     TEXT,
  area_sqft         NUMERIC(14,2),
  location          TEXT,
  acquisition_status TEXT NOT NULL DEFAULT 'identified'
    CHECK (acquisition_status IN ('identified','due_diligence','under_negotiation','acquired','dropped')),
  status            TEXT NOT NULL DEFAULT 'active',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID REFERENCES identity.users(id),
  updated_by        UUID REFERENCES identity.users(id),
  version           INT NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ
);

-- JDA, RERA, and other land/legal approvals.
CREATE TABLE land.land_legal_approvals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  land_parcel_id  UUID REFERENCES land.land_parcels(id),
  project_id      UUID REFERENCES organization.projects(id),
  approval_type   TEXT NOT NULL,   -- JDA, RERA, layout approval, environmental clearance, etc.
  authority       TEXT,
  reference_number TEXT,
  valid_from      DATE,
  valid_to        DATE,
  status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','applied','approved','rejected','expired')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ
);

CREATE TABLE land.due_diligence_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  land_parcel_id  UUID NOT NULL REFERENCES land.land_parcels(id),
  category        TEXT NOT NULL,
  title           TEXT NOT NULL,
  result          TEXT NOT NULL DEFAULT 'pending'
    CHECK (result IN ('pending','clear','issue','waived')),
  evidence_document_id UUID REFERENCES documents.documents(id),
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ
);

-- Loans / EMI / PDCs against land or project financing.
CREATE TABLE land.loan_obligations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id UUID NOT NULL REFERENCES organization.legal_entities(id),
  project_id      UUID REFERENCES organization.projects(id),
  lender_name     TEXT NOT NULL,
  principal_amount NUMERIC(16,2),
  emi_amount      NUMERIC(14,2),
  emi_due_day     INT,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','defaulted')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ
);

CREATE TABLE land.loan_installments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  loan_obligation_id UUID NOT NULL REFERENCES land.loan_obligations(id),
  due_date        DATE NOT NULL,
  amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
  instrument_type TEXT NOT NULL DEFAULT 'emi'
    CHECK (instrument_type IN ('emi','pdc','other')),
  reference_number TEXT,
  status          TEXT NOT NULL DEFAULT 'scheduled'
    CHECK (status IN ('scheduled','paid','bounced','waived','overdue')),
  paid_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ,
  UNIQUE (loan_obligation_id, due_date, instrument_type)
);

CREATE INDEX idx_due_diligence_parcel ON land.due_diligence_items(land_parcel_id);
CREATE INDEX idx_loan_installments_due ON land.loan_installments(due_date, status);

-- =====================================================================
-- SCHEMA: compliance   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS compliance;

CREATE TABLE compliance.rera_registrations (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES organization.projects(id),
  registration_number TEXT NOT NULL,
  valid_from        DATE,
  valid_to          DATE,
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','lapsed','revoked')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID REFERENCES identity.users(id),
  updated_by        UUID REFERENCES identity.users(id),
  version           INTEGER NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ,
  UNIQUE (registration_number)
);

CREATE TABLE compliance.compliance_obligations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id UUID REFERENCES organization.legal_entities(id),
  project_id      UUID REFERENCES organization.projects(id),
  obligation_type TEXT NOT NULL,   -- authority fee, statutory filing, etc.
  authority       TEXT,
  due_date        DATE,
  amount          NUMERIC(14,2),
  status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid','waived','overdue')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ
);

-- =====================================================================
-- SCHEMA: documents   (Blueprint §4, §13 Document Engine)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS documents;

CREATE TABLE documents.documents (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES organization.projects(id),
  building_id    UUID REFERENCES organization.buildings(id),
  floor_id       UUID REFERENCES organization.floors(id),
  unit_id        UUID REFERENCES organization.units(id),
  discipline     TEXT,          -- architectural, structural, MEP, etc.
  drawing_number TEXT,
  document_type  TEXT,
  classification TEXT NOT NULL DEFAULT 'internal' CHECK (classification IN ('public','internal','confidential','restricted')),
  status         TEXT NOT NULL DEFAULT 'uploaded'
    CHECK (status IN ('uploaded','virus_scanned','classified','under_review','approved','issued','superseded','archived')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID REFERENCES identity.users(id),
  updated_by     UUID REFERENCES identity.users(id),
  version        INTEGER NOT NULL DEFAULT 1,
  archived_at    TIMESTAMPTZ
);

CREATE TABLE documents.document_versions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id             UUID NOT NULL REFERENCES documents.documents(id),
  revision_code           TEXT NOT NULL,
  issue_purpose           TEXT,
  issue_date              DATE,
  author_id               UUID REFERENCES identity.users(id),
  reviewer_id             UUID REFERENCES identity.users(id),
  approver_id             UUID REFERENCES identity.users(id),
  superseded_version_id   UUID REFERENCES documents.document_versions(id),
  related_change_request_id UUID,   -- FK added once construction.change_requests exists (Phase 7)
  object_storage_key      TEXT NOT NULL UNIQUE,
  checksum_sha256         TEXT NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  status                  TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN (
      'draft','virus_scanned','quarantined','under_review','approved','issued','superseded'
    )),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, revision_code)
);

CREATE INDEX idx_documents_project ON documents.documents(project_id);
CREATE INDEX idx_document_versions_document ON documents.document_versions(document_id);

CREATE TABLE documents.preview_grants (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID NOT NULL REFERENCES documents.document_versions(id),
  session_id        UUID NOT NULL REFERENCES identity.sessions(id),
  created_by        UUID NOT NULL REFERENCES identity.users(id),
  token_hash        TEXT NOT NULL UNIQUE,
  watermark_text    TEXT NOT NULL,
  expires_at        TIMESTAMPTZ NOT NULL,
  revoked_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE documents.export_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID NOT NULL REFERENCES documents.document_versions(id),
  requested_by      UUID NOT NULL REFERENCES identity.users(id),
  approved_by       UUID REFERENCES identity.users(id),
  reason            TEXT NOT NULL,
  decision_reason   TEXT,
  status            TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','expired','downloaded')),
  expires_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  version           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_preview_grants_expiry
  ON documents.preview_grants(expires_at) WHERE revoked_at IS NULL;
CREATE INDEX idx_export_requests_revision
  ON documents.export_requests(document_version_id, status);
CREATE UNIQUE INDEX uq_export_requests_pending_requester
  ON documents.export_requests(document_version_id, requested_by)
  WHERE status = 'pending';

-- =====================================================================
-- SCHEMA: design   (Blueprint §14 BIM Integration)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS design;

CREATE TABLE design.bim_imports (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID NOT NULL REFERENCES organization.projects(id),
  source_file_reference  TEXT NOT NULL,
  source_document_id     UUID REFERENCES documents.documents(id),
  import_status          TEXT NOT NULL DEFAULT 'received' CHECK (import_status IN ('received','validating','validated','rejected','imported')),
  validated_at           TIMESTAMPTZ,
  validated_by           UUID REFERENCES identity.users(id),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by             UUID REFERENCES identity.users(id),
  updated_by             UUID REFERENCES identity.users(id),
  version                INTEGER NOT NULL DEFAULT 1,
  archived_at            TIMESTAMPTZ
);

CREATE TABLE design.bim_objects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bim_import_id   UUID NOT NULL REFERENCES design.bim_imports(id),
  ifc_guid        TEXT,
  object_type     TEXT,       -- work package, material, asset, etc.
  project_id      UUID REFERENCES organization.projects(id),
  building_id     UUID REFERENCES organization.buildings(id),
  floor_id        UUID REFERENCES organization.floors(id),
  unit_id         UUID REFERENCES organization.units(id),
  room_reference  TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  archived_at     TIMESTAMPTZ,
  UNIQUE (bim_import_id, ifc_guid)
);

-- =====================================================================
-- SCHEMA: quantities   (Blueprint §5.2 CostCode, §9 Quantity Workflow)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS quantities;

CREATE TABLE quantities.cost_codes (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES organization.projects(id),
  code             TEXT NOT NULL,
  description      TEXT,
  wbs_level        INT NOT NULL DEFAULT 1,
  parent_cost_code_id UUID REFERENCES quantities.cost_codes(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by       UUID REFERENCES identity.users(id),
  updated_by       UUID REFERENCES identity.users(id),
  version          INTEGER NOT NULL DEFAULT 1,
  archived_at      TIMESTAMPTZ,
  CHECK (wbs_level >= 1),
  UNIQUE (project_id, code)
);

CREATE TABLE quantities.quantity_items (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID NOT NULL REFERENCES organization.projects(id),
  cost_code_id           UUID REFERENCES quantities.cost_codes(id),
  bim_object_id          UUID REFERENCES design.bim_objects(id),
  work_package           TEXT,
  calculated_quantity    NUMERIC(16,4),
  verified_quantity      NUMERIC(16,4),
  proposed_resolution    TEXT,
  final_approved_quantity NUMERIC(16,4),
  tolerance_pct          NUMERIC(5,2) NOT NULL DEFAULT 2.0,
  status                 TEXT NOT NULL DEFAULT 'calculated'
    CHECK (status IN ('calculated','submitted','within_tolerance','discrepancy','under_review','approved')),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by             UUID REFERENCES identity.users(id),
  updated_by             UUID REFERENCES identity.users(id),
  version                INTEGER NOT NULL DEFAULT 1,
  archived_at            TIMESTAMPTZ,
  CHECK (calculated_quantity IS NULL OR calculated_quantity >= 0),
  CHECK (verified_quantity IS NULL OR verified_quantity >= 0),
  CHECK (final_approved_quantity IS NULL OR final_approved_quantity >= 0),
  CHECK (tolerance_pct BETWEEN 0 AND 100),
  UNIQUE (id, project_id)
);

-- =====================================================================
-- SCHEMA: budget   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS budget;

CREATE TABLE budget.budgets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES organization.projects(id),
  legal_entity_id UUID NOT NULL REFERENCES organization.legal_entities(id),
  total_amount    NUMERIC(16,2) NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','revised')),
  approved_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      UUID REFERENCES identity.users(id),
  updated_by      UUID REFERENCES identity.users(id),
  version         INTEGER NOT NULL DEFAULT 1,
  archived_at     TIMESTAMPTZ,
  CHECK (total_amount >= 0)
);

CREATE TABLE budget.budget_lines (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  budget_id        UUID NOT NULL REFERENCES budget.budgets(id),
  cost_code_id     UUID REFERENCES quantities.cost_codes(id),
  description      TEXT,
  planned_amount   NUMERIC(16,2) NOT NULL DEFAULT 0,
  committed_amount NUMERIC(16,2) NOT NULL DEFAULT 0,
  actual_amount    NUMERIC(16,2) NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'active',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by       UUID REFERENCES identity.users(id),
  updated_by       UUID REFERENCES identity.users(id),
  version          INTEGER NOT NULL DEFAULT 1,
  archived_at      TIMESTAMPTZ,
  CHECK (planned_amount >= 0 AND committed_amount >= 0 AND actual_amount >= 0)
);

CREATE INDEX idx_budget_lines_budget ON budget.budget_lines(budget_id);

-- =====================================================================
-- SCHEMA: procurement   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS procurement;

CREATE TABLE procurement.purchase_orders (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES organization.projects(id),
  vendor_id      UUID NOT NULL REFERENCES organization.vendors(id),
  budget_line_id UUID REFERENCES budget.budget_lines(id),
  total_amount   NUMERIC(16,2) NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','submitted','approved','issued','partially_received','closed','cancelled')),
  issued_at      TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID REFERENCES identity.users(id),
  updated_by     UUID REFERENCES identity.users(id),
  version        INTEGER NOT NULL DEFAULT 1,
  archived_at    TIMESTAMPTZ,
  -- Vendor must be Active (see vendor_onboarding.vendor_onboardings) before a PO can be issued;
  -- enforced at application layer per Blueprint §11 Vendor Onboarding Workflow.
  CONSTRAINT chk_po_amount_nonneg CHECK (total_amount >= 0),
  UNIQUE (id, project_id)
);

CREATE TABLE procurement.purchase_order_lines (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_order_id UUID NOT NULL REFERENCES procurement.purchase_orders(id),
  cost_code_id      UUID REFERENCES quantities.cost_codes(id),
  description       TEXT,
  quantity          NUMERIC(16,4),
  unit_price        NUMERIC(14,2),
  amount            NUMERIC(16,2),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID REFERENCES identity.users(id),
  updated_by        UUID REFERENCES identity.users(id),
  version           INTEGER NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ,
  CHECK (quantity IS NULL OR quantity >= 0),
  CHECK (unit_price IS NULL OR unit_price >= 0),
  CHECK (amount IS NULL OR amount >= 0)
);

-- =====================================================================
-- SCHEMA: contracts   (Blueprint §4, §8 Workflow Engine — Contract Execution state)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS contracts;

CREATE TABLE contracts.contracts (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES organization.projects(id),
  party_id            UUID NOT NULL REFERENCES organization.parties(id),
  contract_type       TEXT,
  value               NUMERIC(16,2),
  status              TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','submitted','under_review','clarification_required','resubmitted',
                       'approved','contract_execution','executed','closed','rejected','cancelled','expired','superseded')),
  execution_method    TEXT,              -- e.g. e-signature provider name
  executed_at         TIMESTAMPTZ,
  executed_document_id UUID REFERENCES documents.documents(id),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by          UUID REFERENCES identity.users(id),
  updated_by          UUID REFERENCES identity.users(id),
  version             INTEGER NOT NULL DEFAULT 1,
  archived_at         TIMESTAMPTZ,
  CHECK (value IS NULL OR value >= 0)
);

CREATE TABLE contracts.contract_milestones (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id  UUID NOT NULL REFERENCES contracts.contracts(id),
  description  TEXT,
  due_date     DATE,
  amount       NUMERIC(14,2),
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','due','paid','disputed')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by   UUID REFERENCES identity.users(id),
  updated_by   UUID REFERENCES identity.users(id),
  version      INTEGER NOT NULL DEFAULT 1,
  archived_at  TIMESTAMPTZ,
  CHECK (amount IS NULL OR amount >= 0)
);

-- =====================================================================
-- SCHEMA: construction   (Blueprint §4, §5.2 EHSIncident)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS construction;

CREATE TABLE construction.schedule_activities (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID NOT NULL REFERENCES organization.projects(id),
  wbs_reference          UUID REFERENCES quantities.cost_codes(id),
  name                   TEXT NOT NULL,
  planned_start          DATE,
  planned_end            DATE,
  actual_start           DATE,
  actual_end             DATE,
  predecessor_activity_id UUID REFERENCES construction.schedule_activities(id),
  status                 TEXT NOT NULL DEFAULT 'not_started'
    CHECK (status IN ('not_started','in_progress','delayed','completed')),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by             UUID REFERENCES identity.users(id),
  updated_by             UUID REFERENCES identity.users(id),
  version                INTEGER NOT NULL DEFAULT 1,
  archived_at            TIMESTAMPTZ,
  CHECK (planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start),
  CHECK (actual_end IS NULL OR actual_start IS NULL OR actual_end >= actual_start),
  UNIQUE (id, project_id)
);

CREATE TABLE construction.site_diary_entries (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id               UUID NOT NULL REFERENCES organization.projects(id),
  entry_date               DATE NOT NULL,
  client_record_id         UUID NOT NULL DEFAULT gen_random_uuid(),
  device_recorded_at       TIMESTAMPTZ,
  weather                  TEXT,
  labour_strength          JSONB,   -- {"mason": 12, "electrician": 4, ...}
  materials_received       JSONB,
  materials_consumed       JSONB,
  equipment_breakdowns     TEXT,
  visitor_log              JSONB,
  site_instructions        TEXT,
  delays_and_reasons       TEXT,
  recorded_by              UUID REFERENCES identity.users(id),
  status                   TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('draft','submitted')),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by               UUID REFERENCES identity.users(id),
  updated_by               UUID REFERENCES identity.users(id),
  version                  INTEGER NOT NULL DEFAULT 1,
  archived_at              TIMESTAMPTZ,
  UNIQUE (project_id, entry_date),
  UNIQUE (project_id, client_record_id)
);

CREATE TABLE construction.ehs_incidents (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES organization.projects(id),
  site_diary_entry_id UUID REFERENCES construction.site_diary_entries(id),
  incident_date       DATE NOT NULL,
  severity            TEXT NOT NULL CHECK (severity IN ('near_miss','minor','major','fatality')),
  description         TEXT,
  corrective_action   TEXT,
  status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','corrective_action_assigned','closed')),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by          UUID REFERENCES identity.users(id),
  updated_by          UUID REFERENCES identity.users(id),
  version             INTEGER NOT NULL DEFAULT 1,
  archived_at         TIMESTAMPTZ
);

CREATE TABLE construction.meeting_registers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES organization.projects(id),
  meeting_date  DATE NOT NULL,
  participants  JSONB,
  decisions     JSONB,
  status        TEXT NOT NULL DEFAULT 'recorded',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE construction.meeting_action_items (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_register_id  UUID NOT NULL REFERENCES construction.meeting_registers(id),
  description          TEXT NOT NULL,
  responsible_user_id  UUID REFERENCES identity.users(id),
  due_date             DATE,
  status               TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','overdue')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Change management (Blueprint §10 Change Workflow)
CREATE TABLE construction.change_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES organization.projects(id),
  description       TEXT NOT NULL,
  schedule_impact   TEXT,
  budget_impact     NUMERIC(14,2),
  evidence_document_id UUID REFERENCES documents.documents(id),
  requested_by      UUID REFERENCES identity.users(id),
  decided_by        UUID REFERENCES identity.users(id),
  decided_at        TIMESTAMPTZ,
  status            TEXT NOT NULL DEFAULT 'requested'
    CHECK (status IN ('requested','feasibility_review','structural_review','revised_drawings',
                       'quantity_impact','budget_impact','procurement_impact','contract_impact',
                       'commercial_quotation','approved','implemented','verified','closed','rejected')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID REFERENCES identity.users(id),
  updated_by        UUID REFERENCES identity.users(id),
  version           INTEGER NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ,
  CHECK (budget_impact IS NULL OR budget_impact >= 0)
);

ALTER TABLE documents.document_versions
  ADD CONSTRAINT fk_document_versions_change_request
  FOREIGN KEY (related_change_request_id) REFERENCES construction.change_requests(id);

CREATE INDEX idx_schedule_activities_project ON construction.schedule_activities(project_id);
CREATE INDEX idx_site_diary_project_date ON construction.site_diary_entries(project_id, entry_date);

-- =====================================================================
-- SCHEMA: quality   (Blueprint §4.2, §5.2 RFI/NCR, §12 RFI/NCR Workflow)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS quality;

-- No-code QA/QC template builder (Blueprint §20 UX Improvements).
CREATE TABLE quality.inspection_templates (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID REFERENCES organization.projects(id),
  work_package  TEXT NOT NULL,     -- e.g. plumbing, electrical, RCC, finishing
  template_name TEXT NOT NULL,
  checklist     JSONB NOT NULL,    -- [{"item": "Pressure test completed", "requires_photo": true}, ...]
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','retired')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID REFERENCES identity.users(id),
  updated_by    UUID REFERENCES identity.users(id),
  version       INTEGER NOT NULL DEFAULT 1,
  archived_at   TIMESTAMPTZ,
  UNIQUE (project_id, template_name)
);

CREATE TABLE quality.inspections (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES organization.projects(id),
  building_id  UUID REFERENCES organization.buildings(id),
  floor_id     UUID REFERENCES organization.floors(id),
  unit_id      UUID REFERENCES organization.units(id),
  template_id  UUID REFERENCES quality.inspection_templates(id),
  inspector_id UUID REFERENCES identity.users(id),
  result       TEXT CHECK (result IN ('pass','fail','pending')),
  photos_ref   JSONB,
  notes        TEXT,
  status       TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','in_progress','completed')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by   UUID REFERENCES identity.users(id),
  updated_by   UUID REFERENCES identity.users(id),
  version      INTEGER NOT NULL DEFAULT 1,
  archived_at  TIMESTAMPTZ,
  UNIQUE (id, project_id)
);

CREATE TABLE construction.progress_updates (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID NOT NULL REFERENCES organization.projects(id),
  schedule_activity_id  UUID NOT NULL REFERENCES construction.schedule_activities(id),
  progress_date         DATE NOT NULL,
  percent_complete      NUMERIC(5,2) NOT NULL CHECK (percent_complete BETWEEN 0 AND 100),
  notes                 TEXT,
  evidence_document_id  UUID REFERENCES documents.documents(id),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by            UUID REFERENCES identity.users(id),
  updated_by            UUID REFERENCES identity.users(id),
  version               INTEGER NOT NULL DEFAULT 1,
  archived_at           TIMESTAMPTZ,
  UNIQUE (schedule_activity_id, progress_date)
);

CREATE TABLE quality.inspection_evidence (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  inspection_id  UUID NOT NULL REFERENCES quality.inspections(id),
  document_id    UUID NOT NULL REFERENCES documents.documents(id),
  evidence_type  TEXT NOT NULL DEFAULT 'photo'
    CHECK (evidence_type IN ('photo','report','certificate','other')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID REFERENCES identity.users(id),
  UNIQUE (inspection_id, document_id)
);

CREATE TABLE quality.snag_items (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID NOT NULL REFERENCES organization.projects(id),
  inspection_id         UUID REFERENCES quality.inspections(id),
  building_id           UUID REFERENCES organization.buildings(id),
  floor_id              UUID REFERENCES organization.floors(id),
  unit_id               UUID REFERENCES organization.units(id),
  description           TEXT NOT NULL,
  severity              TEXT NOT NULL DEFAULT 'minor'
    CHECK (severity IN ('minor','major','critical')),
  assigned_to           UUID REFERENCES identity.users(id),
  due_date              DATE,
  evidence_document_id  UUID REFERENCES documents.documents(id),
  status                TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','assigned','rectified','verified','closed')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by            UUID REFERENCES identity.users(id),
  updated_by            UUID REFERENCES identity.users(id),
  version               INTEGER NOT NULL DEFAULT 1,
  archived_at           TIMESTAMPTZ
);

-- RFI: promoted to a first-class object per audit finding (was folded into discrepancy case in v1).
CREATE TABLE quality.rfis (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES organization.projects(id),
  raised_by    UUID REFERENCES identity.users(id),
  routed_to    UUID REFERENCES identity.users(id),
  question     TEXT NOT NULL,
  response     TEXT,
  evidence_document_id UUID REFERENCES documents.documents(id),
  responded_by UUID REFERENCES identity.users(id),
  responded_at TIMESTAMPTZ,
  sla_due_at   TIMESTAMPTZ,
  status       TEXT NOT NULL DEFAULT 'raised' CHECK (status IN ('raised','routed','responded','closed','overdue')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by   UUID REFERENCES identity.users(id),
  updated_by   UUID REFERENCES identity.users(id),
  version      INTEGER NOT NULL DEFAULT 1,
  archived_at  TIMESTAMPTZ
);

-- NCR: promoted to a first-class object per audit finding.
CREATE TABLE quality.ncrs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES organization.projects(id),
  inspection_id       UUID,
  schedule_activity_id UUID,
  severity            TEXT NOT NULL CHECK (severity IN ('minor','major','critical')),
  description          TEXT NOT NULL,
  corrective_action    TEXT,
  evidence_document_id UUID REFERENCES documents.documents(id),
  closed_by             UUID REFERENCES identity.users(id),
  closed_at             TIMESTAMPTZ,
  reinspection_id      UUID,
  status               TEXT NOT NULL DEFAULT 'raised'
    CHECK (status IN ('raised','corrective_action_assigned','reinspection_scheduled','closed')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by             UUID REFERENCES identity.users(id),
  updated_by             UUID REFERENCES identity.users(id),
  version                INTEGER NOT NULL DEFAULT 1,
  archived_at            TIMESTAMPTZ,
  FOREIGN KEY (inspection_id, project_id) REFERENCES quality.inspections(id, project_id),
  FOREIGN KEY (schedule_activity_id, project_id)
    REFERENCES construction.schedule_activities(id, project_id),
  FOREIGN KEY (reinspection_id, project_id) REFERENCES quality.inspections(id, project_id)
);

-- Discrepancy case remains distinct: used specifically for quantity variances (Blueprint §9).
CREATE TABLE quality.discrepancy_cases (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES organization.projects(id),
  quantity_item_id  UUID,
  description       TEXT,
  evidence_ref      JSONB,
  evidence_document_id UUID REFERENCES documents.documents(id),
  resolved_by       UUID REFERENCES identity.users(id),
  resolved_at       TIMESTAMPTZ,
  proposed_resolution TEXT,
  status            TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','explanation_provided','engineering_review','owner_approval_required','resolved')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        UUID REFERENCES identity.users(id),
  updated_by        UUID REFERENCES identity.users(id),
  version           INTEGER NOT NULL DEFAULT 1,
  archived_at       TIMESTAMPTZ,
  FOREIGN KEY (quantity_item_id, project_id)
    REFERENCES quantities.quantity_items(id, project_id)
);

CREATE INDEX idx_inspections_project ON quality.inspections(project_id);
CREATE INDEX idx_progress_updates_project_date
  ON construction.progress_updates(project_id, progress_date);
CREATE INDEX idx_snag_items_project_status ON quality.snag_items(project_id, status);
CREATE INDEX idx_rfis_project_status ON quality.rfis(project_id, status);
CREATE INDEX idx_ncrs_project_status ON quality.ncrs(project_id, status);
CREATE INDEX idx_change_requests_project_status ON construction.change_requests(project_id, status);
CREATE INDEX idx_discrepancy_cases_project_status ON quality.discrepancy_cases(project_id, status);

-- =====================================================================
-- SCHEMA: inventory   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS inventory;

CREATE TABLE inventory.materials (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  unit_of_measure TEXT NOT NULL,
  category      TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID REFERENCES identity.users(id),
  updated_by    UUID REFERENCES identity.users(id),
  version       INTEGER NOT NULL DEFAULT 1,
  archived_at   TIMESTAMPTZ,
  UNIQUE (name, unit_of_measure)
);

CREATE TABLE inventory.material_receipts (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         UUID NOT NULL REFERENCES organization.projects(id),
  purchase_order_id  UUID,
  material_id        UUID NOT NULL REFERENCES inventory.materials(id),
  quantity_received  NUMERIC(16,4) NOT NULL CHECK (quantity_received > 0),
  batch_reference    TEXT,
  certificate_document_id UUID REFERENCES documents.documents(id),
  received_date      DATE NOT NULL,
  status             TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','rejected','partial')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by         UUID REFERENCES identity.users(id),
  updated_by         UUID REFERENCES identity.users(id),
  version            INTEGER NOT NULL DEFAULT 1,
  archived_at        TIMESTAMPTZ,
  FOREIGN KEY (purchase_order_id, project_id)
    REFERENCES procurement.purchase_orders(id, project_id)
);

CREATE TABLE inventory.material_issuances (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES organization.projects(id),
  material_id   UUID NOT NULL REFERENCES inventory.materials(id),
  material_receipt_id UUID NOT NULL REFERENCES inventory.material_receipts(id),
  quantity_issued NUMERIC(16,4) NOT NULL CHECK (quantity_issued > 0),
  issued_to     TEXT,
  issued_date   DATE NOT NULL,
  evidence_document_id UUID REFERENCES documents.documents(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID REFERENCES identity.users(id),
  updated_by    UUID REFERENCES identity.users(id),
  version       INTEGER NOT NULL DEFAULT 1,
  archived_at   TIMESTAMPTZ
);

CREATE INDEX idx_bim_imports_project ON design.bim_imports(project_id);
CREATE INDEX idx_quantity_items_project_status ON quantities.quantity_items(project_id, status);
CREATE INDEX idx_material_receipts_project_date ON inventory.material_receipts(project_id, received_date);
CREATE INDEX idx_material_issuances_receipt ON inventory.material_issuances(material_receipt_id);

-- =====================================================================
-- SCHEMA: sales   (Blueprint §4.2 — CRM lead funnel / channel-partner commission)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.channel_partners (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                   TEXT NOT NULL,
  commission_structure   JSONB,
  status                 TEXT NOT NULL DEFAULT 'active',
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales.leads (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         UUID REFERENCES organization.projects(id),
  source             TEXT,          -- website, walk-in, channel partner, referral
  channel_partner_id UUID REFERENCES sales.channel_partners(id),
  assigned_to        UUID REFERENCES identity.users(id),
  status             TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','site_visit','negotiation','converted','lost')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- SCHEMA: customers   (Blueprint §4)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS customers;

CREATE TABLE customers.customers (
  id         UUID PRIMARY KEY REFERENCES organization.parties(id),
  kyc_status TEXT NOT NULL DEFAULT 'pending' CHECK (kyc_status IN ('pending','verified','rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers.bookings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id   UUID NOT NULL REFERENCES customers.customers(id),
  unit_id       UUID NOT NULL REFERENCES organization.units(id),
  project_id    UUID NOT NULL REFERENCES organization.projects(id),
  lead_id       UUID REFERENCES sales.leads(id),
  booking_date  DATE NOT NULL,
  status        TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked','cancelled','registered','possessed')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales.commissions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_partner_id UUID NOT NULL REFERENCES sales.channel_partners(id),
  booking_id         UUID NOT NULL REFERENCES customers.bookings(id),
  amount             NUMERIC(14,2),
  status             TEXT NOT NULL DEFAULT 'accrued' CHECK (status IN ('accrued','approved','paid')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers.payment_plans (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id   UUID NOT NULL REFERENCES customers.bookings(id),
  plan_name    TEXT,
  total_amount NUMERIC(16,2),
  status       TEXT NOT NULL DEFAULT 'active',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers.payment_plan_installments (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_plan_id  UUID NOT NULL REFERENCES customers.payment_plans(id),
  due_date         DATE,
  amount           NUMERIC(14,2),
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','collected','overdue','waived')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers.collections (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id     UUID NOT NULL REFERENCES customers.bookings(id),
  installment_id UUID REFERENCES customers.payment_plan_installments(id),
  amount         NUMERIC(14,2) NOT NULL,
  received_date  DATE NOT NULL,
  mode           TEXT,   -- cheque, NEFT, PDC, etc.
  reference_number TEXT,
  status         TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','bounced','allocated')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers.possession_records (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id    UUID NOT NULL REFERENCES customers.bookings(id),
  handover_date DATE,
  status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','snag_review','handed_over')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bookings_project ON customers.bookings(project_id);
CREATE INDEX idx_collections_booking ON customers.collections(booking_id);

-- =====================================================================
-- SCHEMA: finance   (Blueprint §16 Tally Reconciliation)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE finance.tally_vouchers (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id  UUID NOT NULL REFERENCES organization.legal_entities(id),
  voucher_type     TEXT,
  voucher_number   TEXT,
  voucher_date     DATE,
  amount           NUMERIC(16,2),
  ledger_reference TEXT,
  imported_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  status           TEXT NOT NULL DEFAULT 'imported' CHECK (status IN ('imported','matched','discrepant'))
);

CREATE TABLE finance.reconciliations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id    UUID NOT NULL REFERENCES organization.legal_entities(id),
  erp_reference_type TEXT NOT NULL,   -- 'purchase_order','contract_milestone','collection', etc.
  erp_reference_id   UUID NOT NULL,
  tally_voucher_id   UUID REFERENCES finance.tally_vouchers(id),
  discrepancy_type   TEXT,            -- missing_in_tally, missing_in_erp, amount_mismatch, wrong_entity, wrong_project, duplicate, unallocated_receipt
  status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','under_review','reconciled')),
  reviewed_by        UUID REFERENCES identity.users(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE finance.payments (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         UUID REFERENCES organization.projects(id),
  party_id           UUID REFERENCES organization.parties(id),
  contract_id        UUID REFERENCES contracts.contracts(id),
  amount             NUMERIC(16,2) NOT NULL,
  payment_date       DATE,
  status             TEXT NOT NULL DEFAULT 'pending_approval'
    CHECK (status IN ('pending_approval','approved','released','rejected')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- SCHEMA: workflow   (Blueprint §8 Workflow Engine)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS workflow;

CREATE TABLE workflow.workflow_definitions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  version     INT NOT NULL DEFAULT 1,
  states      JSONB NOT NULL,   -- ordered state list + transition rules
  status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','retired')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);

CREATE TABLE workflow.workflow_instances (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_definition_id  UUID NOT NULL REFERENCES workflow.workflow_definitions(id),
  subject_type            TEXT NOT NULL,   -- 'contract','quantity_item','change_request', etc.
  subject_id               UUID NOT NULL,
  current_state            TEXT NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow.approval_requests (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_instance_id UUID NOT NULL REFERENCES workflow.workflow_instances(id),
  requested_by        UUID REFERENCES identity.users(id),
  approver_id         UUID REFERENCES identity.users(id),
  threshold_amount    NUMERIC(16,2),
  quorum_rule         TEXT,
  status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','escalated','delegated')),
  decided_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow.tasks (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id           UUID REFERENCES organization.projects(id),
  workflow_instance_id UUID REFERENCES workflow.workflow_instances(id),
  assigned_to          UUID REFERENCES identity.users(id),
  description          TEXT NOT NULL,
  due_date             DATE,
  source               TEXT NOT NULL DEFAULT 'human' CHECK (source IN ('human','ai_proposed')),
  status               TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','done','cancelled')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_instances_subject ON workflow.workflow_instances(subject_type, subject_id);
CREATE INDEX idx_approval_requests_instance ON workflow.approval_requests(workflow_instance_id);
CREATE INDEX idx_tasks_assigned_to ON workflow.tasks(assigned_to);

-- =====================================================================
-- SCHEMA: communications   (Blueprint §18 Event & Notification Architecture)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS communications;

-- Event layer: Postgres LISTEN/NOTIFY at current scale (Blueprint §7.1, §18).
CREATE TABLE communications.notification_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type   TEXT NOT NULL,     -- e.g. 'workflow.state_changed'
  subject_type TEXT NOT NULL,
  subject_id   UUID NOT NULL,
  payload      JSONB NOT NULL,
  published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE communications.notifications (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_event_id UUID REFERENCES communications.notification_events(id),
  recipient_user_id     UUID REFERENCES identity.users(id),
  channel               TEXT NOT NULL DEFAULT 'in_app' CHECK (channel IN ('in_app','email','sms')),
  sent_at                TIMESTAMPTZ,
  status                 TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed')),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE communications.communication_tasks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID REFERENCES organization.projects(id),
  task_type      TEXT,     -- vendor agreement, demand letter, payment reminder, etc.
  draft_content  TEXT,
  drafted_by_ai  BOOLEAN NOT NULL DEFAULT false,
  approved_by    UUID REFERENCES identity.users(id),
  sent_at        TIMESTAMPTZ,
  status         TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','sent','discarded')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Publish a notification event on every workflow state change (Blueprint §18).
CREATE OR REPLACE FUNCTION workflow.publish_state_change_event() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.current_state IS DISTINCT FROM OLD.current_state THEN
    INSERT INTO communications.notification_events (event_type, subject_type, subject_id, payload)
    VALUES ('workflow.state_changed', NEW.subject_type, NEW.subject_id,
            jsonb_build_object('workflow_instance_id', NEW.id, 'from_state', OLD.current_state, 'to_state', NEW.current_state));
    PERFORM pg_notify('workflow_state_changed', NEW.id::text);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_publish_state_change
  AFTER UPDATE ON workflow.workflow_instances
  FOR EACH ROW EXECUTE FUNCTION workflow.publish_state_change_event();

-- =====================================================================
-- SCHEMA: ai   (Blueprint §17 AI Architecture)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS ai;

CREATE TABLE ai.ai_queries (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID REFERENCES identity.users(id),
  query_text           TEXT NOT NULL,
  intent_classification TEXT,
  response_text        TEXT,
  confidence           NUMERIC(4,3),   -- 0.000–1.000; below Phase-11 minimum threshold, AI must decline
  required_approver    UUID REFERENCES identity.users(id),
  status               TEXT NOT NULL DEFAULT 'answered' CHECK (status IN ('answered','declined_low_confidence','blocked_authority')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.ai_recommendations (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ai_query_id        UUID NOT NULL REFERENCES ai.ai_queries(id),
  recommendation_text TEXT NOT NULL,
  financial_impact   NUMERIC(16,2),
  schedule_impact    TEXT,
  risk_level         TEXT CHECK (risk_level IN ('low','medium','high')),
  status             TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','rejected','superseded')),
  approved_by        UUID REFERENCES identity.users(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Authority-boundary log: every attempted action is logged, including blocked ones —
-- feeds the pre-launch red-team exercise (Blueprint §17.1).
CREATE TABLE ai.ai_authority_log (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ai_query_id      UUID REFERENCES ai.ai_queries(id),
  authority_level  INT NOT NULL CHECK (authority_level BETWEEN 1 AND 4),
  action_attempted TEXT NOT NULL,
  blocked          BOOLEAN NOT NULL DEFAULT false,
  reason           TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- SCHEMA: audit   (Blueprint §5.2 — hash-chained AuditEvent)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS audit;

-- Chain position allocator. Deliberately NOT wired as a column DEFAULT (i.e.
-- not BIGSERIAL): a default is evaluated before BEFORE-INSERT triggers run,
-- so numbers would be handed out before the chain lock is taken and seq order
-- would not match chain linkage. compute_record_hash() calls nextval() itself,
-- inside the lock. See the trigger below.
CREATE SEQUENCE audit.audit_events_seq;

CREATE TABLE audit.audit_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Monotonic chain position. id is a random UUID and created_at is
  -- transaction-scoped (identical for every row written in one transaction),
  -- so neither can order the hash chain. seq is the only ordering key the
  -- chain may use — in the trigger below and in any verifier. Assigned by
  -- the trigger, not by a default; see audit.audit_events_seq above.
  seq           BIGINT NOT NULL UNIQUE,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_user_id UUID REFERENCES identity.users(id),
  entity_schema TEXT NOT NULL,
  entity_table  TEXT NOT NULL,
  entity_id     UUID,
  action        TEXT NOT NULL,     -- 'create','update','approve','reject','delete_attempt', etc.
  before_state  JSONB,
  after_state   JSONB,
  prev_hash     TEXT NOT NULL,
  record_hash   TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only enforcement: no UPDATE or DELETE, ever.
CREATE OR REPLACE FUNCTION audit.reject_modification() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit.audit_events is append-only; % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit.audit_events
  FOR EACH ROW EXECUTE FUNCTION audit.reject_modification();
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit.audit_events
  FOR EACH ROW EXECUTE FUNCTION audit.reject_modification();

-- Hash chain: each record's hash covers the previous record's hash plus its own content,
-- so any retroactive edit (bypassing the append-only trigger via superuser, e.g.) is detectable
-- by recomputing the chain (Blueprint §5.2, closes Audit Section 16 item 4).
CREATE OR REPLACE FUNCTION audit.compute_record_hash() RETURNS trigger AS $$
DECLARE
  last_hash TEXT;
BEGIN
  -- Chain construction is inherently serial: two concurrent inserts that both
  -- read the same predecessor would fork the chain. Serialise appenders on a
  -- transaction-scoped advisory lock. Held until commit, so the reader below
  -- and the eventual insert are atomic with respect to other appenders.
  PERFORM pg_advisory_xact_lock(hashtext('audit.audit_events'));

  -- Allocate the chain position under the lock, so seq order and hash linkage
  -- can never disagree. (A BIGSERIAL default would be evaluated before this
  -- trigger body runs, allowing a writer holding seq=N to chain onto seq=N+1.)
  NEW.seq := nextval('audit.audit_events_seq');

  SELECT record_hash INTO last_hash FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := COALESCE(last_hash, repeat('0', 64));
  -- occurred_at is normalised to UTC and formatted explicitly rather than cast
  -- with ::text. A timestamptz cast renders through the *session's* TimeZone
  -- and DateStyle settings, so the same instant written by a client on
  -- Asia/Kolkata and verified by one on UTC would hash to two different values
  -- and the chain would read as tampered. to_char with a fixed pattern is
  -- stable across both settings and always emits 6 fractional digits.
  NEW.record_hash := encode(
    digest(
      NEW.prev_hash || NEW.entity_schema || NEW.entity_table ||
      COALESCE(NEW.entity_id::text, '') || NEW.action ||
      COALESCE(NEW.after_state::text, '') ||
      to_char(NEW.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US'),
      'sha256'
    ),
    'hex'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_compute_hash BEFORE INSERT ON audit.audit_events
  FOR EACH ROW EXECUTE FUNCTION audit.compute_record_hash();

CREATE INDEX idx_audit_events_entity ON audit.audit_events(entity_schema, entity_table, entity_id);
CREATE INDEX idx_audit_events_occurred_at ON audit.audit_events(occurred_at);

-- =====================================================================
-- SCHEMA: vendor_onboarding   (NEW — Blueprint §4.2, §5.2, §11)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS vendor_onboarding;

CREATE TABLE vendor_onboarding.vendor_onboardings (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_id                   UUID NOT NULL REFERENCES organization.vendors(id),
  status                      TEXT NOT NULL DEFAULT 'invited'
    CHECK (status IN ('invited','kyc_submitted','bank_verified','compliance_docs_submitted','approved','active','rejected')),
  invited_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  kyc_completed_at            TIMESTAMPTZ,
  bank_verified_at            TIMESTAMPTZ,
  compliance_docs_completed_at TIMESTAMPTZ,
  approved_at                 TIMESTAMPTZ,
  approved_by                 UUID REFERENCES identity.users(id),
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by                  UUID REFERENCES identity.users(id),
  updated_by                  UUID REFERENCES identity.users(id),
  version                     INTEGER NOT NULL DEFAULT 1,
  archived_at                 TIMESTAMPTZ,
  UNIQUE (vendor_id)
);

CREATE TABLE vendor_onboarding.kyc_records (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id            UUID NOT NULL REFERENCES organization.parties(id),   -- vendor or customer
  document_type       TEXT NOT NULL,   -- GST, PAN, bank proof, incorporation certificate, etc.
  document_reference  TEXT,
  object_storage_key  TEXT,
  verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending','verified','rejected')),
  verified_by         UUID REFERENCES identity.users(id),
  verified_at         TIMESTAMPTZ,
  evidence_document_id UUID REFERENCES documents.documents(id),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by          UUID REFERENCES identity.users(id),
  updated_by          UUID REFERENCES identity.users(id),
  version             INTEGER NOT NULL DEFAULT 1,
  archived_at         TIMESTAMPTZ
);

CREATE TABLE vendor_onboarding.insurance_policies (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID REFERENCES organization.projects(id),
  contract_id    UUID REFERENCES contracts.contracts(id),
  vendor_id      UUID REFERENCES organization.vendors(id),
  policy_number  TEXT NOT NULL,
  insurer        TEXT,
  coverage_type  TEXT NOT NULL CHECK (coverage_type IN ('CAR','professional_indemnity','other')),
  sum_insured    NUMERIC(16,2),
  valid_from     DATE,
  valid_to       DATE,
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','claimed','cancelled')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID REFERENCES identity.users(id),
  updated_by     UUID REFERENCES identity.users(id),
  version        INTEGER NOT NULL DEFAULT 1,
  archived_at    TIMESTAMPTZ,
  CHECK (sum_insured IS NULL OR sum_insured >= 0)
);

CREATE TABLE vendor_onboarding.labour_compliance_records (
  id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contractor_id                 UUID NOT NULL REFERENCES organization.contractors(id),
  project_id                    UUID REFERENCES organization.projects(id),
  pf_registration_number        TEXT,
  esi_registration_number       TEXT,
  contract_labour_licence_number TEXT,
  minimum_wage_evidence_ref     TEXT,
  status                        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','compliant','non_compliant')),
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by                    UUID REFERENCES identity.users(id),
  updated_by                    UUID REFERENCES identity.users(id),
  version                       INTEGER NOT NULL DEFAULT 1,
  archived_at                   TIMESTAMPTZ
);

CREATE INDEX idx_kyc_records_party ON vendor_onboarding.kyc_records(party_id);
CREATE INDEX idx_insurance_policies_project ON vendor_onboarding.insurance_policies(project_id);

-- =====================================================================
-- SCHEMA: reporting   (NEW — Blueprint §19; populated via logical replication)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS reporting;

-- No base tables here by design: this schema is fed by logical replication
-- (or, at minimum, a nightly materialized-view refresh) from the transactional
-- schemas above, so CEO-dashboard and analytics queries never compete with
-- operational writes (Blueprint §19). Materialized views are added once each
-- source module ships — e.g., after Phase 4:
--
--   CREATE MATERIALIZED VIEW reporting.mv_budget_vs_actual AS
--     SELECT project_id, SUM(planned_amount) AS planned, SUM(actual_amount) AS actual
--     FROM budget.budget_lines GROUP BY project_id;
--
-- and refreshed on a schedule by a background worker (Blueprint §7.1).

-- =====================================================================
-- Auto-attach the updated_at trigger to every table that has that column.
-- Keeps this file from repeating "CREATE TRIGGER ... set_updated_at" ~40 times.
-- =====================================================================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT table_schema, table_name FROM information_schema.columns
    WHERE column_name = 'updated_at'
      AND table_schema NOT IN ('pg_catalog','information_schema')
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_set_updated_at ON %I.%I', r.table_schema, r.table_name);
    EXECUTE format(
      'CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
      r.table_schema, r.table_name
    );
  END LOOP;
END $$;

-- =====================================================================
-- End of schema.sql
-- Not yet included (deliberately — see Blueprint §25 Open Decisions):
--   - Row-level security policies (depends on the finalized role/permission
--     matrix from Phase 0).
--   - Reporting schema's materialized views (depends on Phase 4+ data existing).
--   - Object-storage-side encryption key references (depends on the KMS/HSM
--     product decision in Blueprint §3.3).
-- =====================================================================
