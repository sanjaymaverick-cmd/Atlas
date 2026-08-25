// Mirrors atlas/api/schemas.py. Hand-written rather than generated from the
// OpenAPI document so the client stays small and reviewable; if this drifts,
// the backend is the source of truth.

export interface Project {
  id: string;
  legal_entity_id: string;
  name: string;
  code: string;
  city: string | null;
  status: string;
  start_date: string | null;
  target_completion_date: string | null;
  version: number;
  archived_at: string | null;
}

export interface ProjectCreate {
  name: string;
  code: string;
  city?: string | null;
  status?: string;
  start_date?: string | null;
  target_completion_date?: string | null;
}

/** The `{"error": {...}}` envelope every failure shares. See atlas/api/errors.py. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface SessionGrant {
  session_token: string;
  token_type: string;
  expires_at: string;
}

export interface CeremonyOptions {
  ceremony_id: string;
  public_key: Record<string, unknown>;
}

export interface AtlasDocument {
  id: string;
  project_id: string;
  discipline: string | null;
  drawing_number: string | null;
  document_type: string | null;
  classification: string;
  status: string;
  version: number;
  archived_at: string | null;
}

export interface DocumentRevision {
  id: string;
  document_id: string;
  revision_code: string;
  issue_purpose: string | null;
  issue_date: string | null;
  author_id: string | null;
  superseded_version_id: string | null;
  object_storage_key: string;
  checksum_sha256: string;
  status: string;
  created_at: string;
}

export interface LandParcel {
  id: string;
  legal_entity_id: string;
  project_id: string | null;
  survey_number: string | null;
  area_sqft: number | string | null;
  location: string | null;
  acquisition_status: string;
  status: string;
  version: number;
  archived_at: string | null;
}

export interface Budget {
  id: string;
  project_id: string;
  legal_entity_id: string;
  total_amount: number | string;
  status: string;
  approved_at: string | null;
  version: number;
  archived_at: string | null;
}

export interface ProjectDashboard {
  project_id: string;
  legal_entity_id: string;
  planned_amount: number | string;
  committed_amount: number | string;
  actual_amount: number | string;
  approved_po_amount: number | string;
  released_payment_amount: number | string;
  allocated_collection_amount: number | string;
  outstanding_receivable_amount: number | string;
  unallocated_collection_count: number;
  overdue_installment_count: number;
  delayed_activity_count: number;
  failed_inspection_count: number;
  open_compliance_count: number;
  open_reconciliation_count: number;
  total_unit_count: number;
  available_unit_count: number;
  committed_unit_count: number;
  refreshed_at: string;
}

export interface EntityDashboard {
  legal_entity_id: string;
  project_count: number;
  planned_amount: number | string;
  committed_amount: number | string;
  actual_amount: number | string;
  released_payment_amount: number | string;
  allocated_collection_amount: number | string;
  outstanding_receivable_amount: number | string;
  delayed_activity_count: number;
  failed_inspection_count: number;
  open_compliance_count: number;
  available_unit_count: number;
  refreshed_at: string;
}
