// Registers for the modules that used to have none.
//
// Added 2026-08-20, once these six modules gained read endpoints. Before that
// the API published 104 writes against 11 reads, none of them here, and a
// Workflows screen with no tables was the honest shape. It has tables now.
//
// Columns are taken from the actual `*Summary` dataclasses, not guessed. That
// matters more than it sounds: several summaries deliberately omit the
// free-text they were created with. A change request has a description and an
// NCR has one too, but neither appears in its summary, because Phase 7 keeps
// confidential narrative out of the service contract entirely. Adding a
// "Description" column would have rendered a permanent em dash and read as
// missing data rather than as a privacy boundary being enforced — so those
// registers carry a note instead.

export interface RegisterColumn {
  header: string;
  field: string;
  kind?: "mono" | "pill" | "date" | "amount";
}

export interface Register {
  key: string;
  title: string;
  scope: "project" | "entity";
  path: (scope: { entity: string; project: string }) => string;
  columns: RegisterColumn[];
  empty: string;
  /** Shown under the title — used where the API withholds fields by design. */
  note?: string;
}

const STATUS: RegisterColumn = { header: "Status", field: "status", kind: "pill" };
const NARRATIVE_WITHHELD =
  "Free-text is deliberately absent from this register: the service contract omits confidential narrative, so it is never returned to a list.";

export const REGISTERS: Record<string, Register[]> = {
  "Phase 3": [
    {
      key: "rera",
      title: "RERA registrations",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/rera-registrations`,
      columns: [
        { header: "Number", field: "registration_number", kind: "mono" },
        { header: "Valid from", field: "valid_from", kind: "date" },
        { header: "Valid to", field: "valid_to", kind: "date" },
        STATUS,
      ],
      empty: "No RERA registrations for this project.",
    },
    {
      key: "obligations",
      title: "Statutory obligations",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/compliance-obligations`,
      columns: [
        { header: "Type", field: "obligation_type" },
        { header: "Authority", field: "authority" },
        { header: "Due", field: "due_date", kind: "date" },
        { header: "Amount", field: "amount", kind: "amount" },
        STATUS,
      ],
      empty: "No statutory obligations recorded.",
    },
  ],
  "Phase 5": [
    {
      key: "activities",
      title: "Schedule activities",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/schedule-activities`,
      columns: [
        { header: "Name", field: "name" },
        { header: "Planned start", field: "planned_start", kind: "date" },
        { header: "Planned end", field: "planned_end", kind: "date" },
        { header: "Actual end", field: "actual_end", kind: "date" },
        STATUS,
      ],
      empty: "No schedule activities for this project.",
    },
    {
      key: "diary",
      title: "Site diary",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/site-diary`,
      columns: [
        { header: "Entry date", field: "entry_date", kind: "date" },
        { header: "Client record", field: "client_record_id", kind: "mono" },
        STATUS,
      ],
      empty: "No site diary entries.",
      note: "Weather, labour, instructions and delay narrative stay out of the summary; the client record ID is the device idempotency key that makes offline capture safe.",
    },
    {
      key: "ehs",
      title: "EHS incidents",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/ehs-incidents`,
      columns: [
        { header: "Date", field: "incident_date", kind: "date" },
        { header: "Severity", field: "severity", kind: "pill" },
        STATUS,
      ],
      empty: "No EHS incidents recorded.",
      note: NARRATIVE_WITHHELD,
    },
    {
      key: "inspections",
      title: "Inspections",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/inspections`,
      columns: [
        { header: "Template", field: "template_id", kind: "mono" },
        { header: "Inspector", field: "inspector_id", kind: "mono" },
        { header: "Result", field: "result", kind: "pill" },
        STATUS,
      ],
      empty: "No inspections scheduled.",
    },
    {
      key: "snags",
      title: "Snags",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/snags`,
      columns: [
        { header: "Description", field: "description" },
        { header: "Severity", field: "severity", kind: "pill" },
        { header: "Assigned to", field: "assigned_to", kind: "mono" },
        { header: "Due", field: "due_date", kind: "date" },
        STATUS,
      ],
      empty: "No snags raised.",
    },
  ],
  "Phase 6": [
    {
      key: "bim",
      title: "BIM imports",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/bim-imports`,
      columns: [
        { header: "Source document", field: "source_document_id", kind: "mono" },
        { header: "Validated", field: "validated_at", kind: "date" },
        STATUS,
      ],
      empty: "No BIM imports registered.",
    },
    {
      key: "cost-codes",
      title: "Cost codes",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/cost-codes`,
      columns: [
        { header: "Code", field: "code", kind: "mono" },
        { header: "Description", field: "description" },
        { header: "WBS level", field: "wbs_level", kind: "mono" },
      ],
      empty: "No cost codes defined.",
    },
    {
      key: "quantities",
      title: "Quantity items",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/quantity-items`,
      columns: [
        { header: "Calculated", field: "calculated_quantity", kind: "amount" },
        { header: "Verified", field: "verified_quantity", kind: "amount" },
        { header: "Approved", field: "final_approved_quantity", kind: "amount" },
        { header: "Tolerance %", field: "tolerance_pct", kind: "amount" },
        STATUS,
      ],
      empty: "No quantity items.",
      note: "Calculated, verified and approved are separate columns on purpose — verification and approval are distinct acts, by different people.",
    },
    {
      key: "receipts",
      title: "Material receipts",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/material-receipts`,
      columns: [
        { header: "Received", field: "received_date", kind: "date" },
        { header: "Material", field: "material_id", kind: "mono" },
        { header: "Quantity", field: "quantity_received", kind: "amount" },
        STATUS,
      ],
      empty: "No material receipts.",
    },
  ],
  "Phase 7": [
    {
      key: "changes",
      title: "Change requests",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/change-requests`,
      columns: [
        { header: "Reference", field: "id", kind: "mono" },
        { header: "Evidence", field: "evidence_document_id", kind: "mono" },
        { header: "Decided", field: "decided_at", kind: "date" },
        STATUS,
      ],
      empty: "No change requests raised.",
      note: NARRATIVE_WITHHELD,
    },
    {
      key: "rfis",
      title: "RFIs",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/rfis`,
      columns: [
        { header: "Routed to", field: "routed_to", kind: "mono" },
        { header: "SLA due", field: "sla_due_at", kind: "date" },
        { header: "Responded", field: "responded_at", kind: "date" },
        STATUS,
      ],
      empty: "No RFIs raised.",
      note: NARRATIVE_WITHHELD,
    },
    {
      key: "ncrs",
      title: "NCRs",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/ncrs`,
      columns: [
        { header: "Severity", field: "severity", kind: "pill" },
        { header: "Reinspection", field: "reinspection_id", kind: "mono" },
        { header: "Closed", field: "closed_at", kind: "date" },
        STATUS,
      ],
      empty: "No non-conformances raised.",
      note: NARRATIVE_WITHHELD,
    },
    {
      key: "discrepancies",
      title: "Discrepancy cases",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/discrepancy-cases`,
      columns: [
        { header: "Quantity item", field: "quantity_item_id", kind: "mono" },
        { header: "Resolved", field: "resolved_at", kind: "date" },
        STATUS,
      ],
      empty: "No discrepancy cases open.",
      note: NARRATIVE_WITHHELD,
    },
  ],
  "Phase 8": [
    {
      key: "bookings",
      title: "Bookings",
      scope: "project",
      path: (s) => `/api/v1/projects/${s.project}/bookings`,
      columns: [
        { header: "Booking date", field: "booking_date", kind: "date" },
        { header: "Unit", field: "unit_id", kind: "mono" },
        { header: "Customer", field: "customer_id", kind: "mono" },
        STATUS,
      ],
      empty: "No bookings for this project.",
      note: "Customers and units appear as opaque IDs: no party identity crosses this boundary.",
    },
  ],
  "Phase 9": [
    {
      key: "batches",
      title: "Tally import batches",
      scope: "entity",
      path: (s) => `/api/v1/legal-entities/${s.entity}/tally-imports`,
      columns: [
        { header: "Period start", field: "period_start", kind: "date" },
        { header: "Period end", field: "period_end", kind: "date" },
        { header: "SHA-256", field: "content_sha256", kind: "mono" },
        STATUS,
      ],
      empty: "No Tally exports registered.",
      note: "The export itself stays in a restricted Documents record; only its provenance hash appears here.",
    },
    {
      key: "reconciliations",
      title: "Reconciliation cases",
      scope: "entity",
      path: (s) => `/api/v1/legal-entities/${s.entity}/reconciliations`,
      columns: [
        { header: "Type", field: "discrepancy_type", kind: "pill" },
        { header: "ERP amount", field: "erp_amount", kind: "amount" },
        { header: "Tally amount", field: "tally_amount", kind: "amount" },
        { header: "Resolution", field: "resolution_code", kind: "mono" },
        STATUS,
      ],
      empty: "No reconciliation cases open.",
    },
  ],
};
