import type { Field } from "../components/ActionForm";

// Every write the API exposes for the six modules that have no read endpoints.
//
// Atlas publishes 104 POST endpoints and 11 GET ones. Change control,
// compliance, construction/quality, customer lifecycle, finance and project
// controls have no GETs at all, so there is nothing to build a register or a
// detail page from. What can honestly be built is the write side: these
// descriptors.
//
// Where an endpoint identifies its target in the path, the id is a form field
// (`pathFields`) rather than a row you clicked, because there is no list to
// click from. That is a limitation of the API, and the UI says so rather than
// hiding it.
//
// Field names, requiredness and status vocabularies are taken from the live
// OpenAPI document and db/schema.sql, not invented.

export interface Workflow {
  key: string;
  title: string;
  description?: string;
  /** Which scope values the path needs. */
  scope: "project" | "entity" | "none";
  /** Builds the path from scope plus any entered path fields. */
  path: (scope: { entity: string; project: string }, values: Record<string, string>) => string;
  fields: Field[];
  pathFields?: string[];
  submitLabel: string;
}

export interface WorkflowGroup {
  phase: string;
  title: string;
  blurb: string;
  workflows: Workflow[];
}

const targetId = (label: string, help?: string): Field => ({
  name: "__id",
  label,
  kind: "uuid",
  required: true,
  placeholder: "00000000-0000-0000-0000-000000000000",
  ...(help ? { help } : {}),
});

const status = (options: string[]): Field => ({
  name: "target_status",
  label: "Target status",
  kind: "select",
  required: true,
  options,
  help: "Transitions are ordered; an invalid jump is rejected as a conflict.",
});

const evidence: Field = {
  name: "evidence_document_id",
  label: "Evidence document ID",
  kind: "uuid",
  help: "Must be a controlled Documents record, never a path or URL.",
};

export const CATALOG: WorkflowGroup[] = [
  {
    phase: "Phase 3",
    title: "Compliance",
    blurb: "RERA registrations and statutory obligations.",
    workflows: [
      {
        key: "rera-create",
        title: "Register a RERA registration",
        description: "The registration number is unique across every project.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/rera-registrations`,
        fields: [
          { name: "registration_number", label: "Registration number", kind: "text", required: true },
          { name: "valid_from", label: "Valid from", kind: "date" },
          { name: "valid_to", label: "Valid to", kind: "date" },
        ],
        submitLabel: "Register",
      },
      {
        key: "rera-transition",
        title: "Move a RERA registration",
        scope: "none",
        path: (_s, v) => `/api/v1/rera-registrations/${v["__id"] ?? ""}/transition`,
        fields: [targetId("Registration ID"), status(["active", "lapsed", "revoked"])],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "obligation-create",
        title: "Record a statutory obligation",
        scope: "none",
        path: () => `/api/v1/compliance-obligations`,
        fields: [
          { name: "obligation_type", label: "Obligation type", kind: "text", required: true },
          { name: "authority", label: "Authority", kind: "text" },
          { name: "due_date", label: "Due date", kind: "date" },
          { name: "amount", label: "Amount", kind: "number" },
        ],
        submitLabel: "Record obligation",
      },
      {
        key: "obligation-transition",
        title: "Move an obligation",
        scope: "none",
        path: (_s, v) => `/api/v1/compliance-obligations/${v["__id"] ?? ""}/transition`,
        fields: [targetId("Obligation ID"), status(["open", "paid", "waived", "overdue"])],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
    ],
  },
  {
    phase: "Phase 5",
    title: "Construction and quality",
    blurb: "Schedule, site diaries, EHS, inspections and snags.",
    workflows: [
      {
        key: "activity-create",
        title: "Add a schedule activity",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/schedule-activities`,
        fields: [
          { name: "name", label: "Name", kind: "text", required: true },
          { name: "wbs_reference", label: "WBS reference", kind: "text" },
          { name: "planned_start", label: "Planned start", kind: "date" },
          { name: "planned_end", label: "Planned end", kind: "date" },
        ],
        submitLabel: "Add activity",
      },
      {
        key: "activity-progress",
        title: "Record progress",
        scope: "none",
        path: (_s, v) => `/api/v1/schedule-activities/${v["__id"] ?? ""}/progress`,
        fields: [
          targetId("Activity ID"),
          { name: "progress_date", label: "Progress date", kind: "date", required: true },
          {
            name: "percent_complete",
            label: "Percent complete",
            kind: "number",
            required: true,
            help: "The database rejects anything outside 0–100.",
          },
          { name: "notes", label: "Notes", kind: "text" },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Record progress",
      },
      {
        key: "activity-transition",
        title: "Move a schedule activity",
        scope: "none",
        path: (_s, v) => `/api/v1/schedule-activities/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Activity ID"),
          status(["not_started", "in_progress", "delayed", "completed"]),
          { name: "corrective_action", label: "Corrective action", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "site-diary",
        title: "Submit a site diary entry",
        description:
          "client_record_id is the device's idempotency key — replaying the same one is rejected, which is what makes offline capture safe.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/site-diary`,
        fields: [
          { name: "entry_date", label: "Entry date", kind: "date", required: true },
          {
            name: "client_record_id",
            label: "Client record ID",
            kind: "uuid",
            required: true,
            help: "Generated on the device. The same value is never accepted twice for a project.",
          },
          { name: "weather", label: "Weather", kind: "text" },
          {
            name: "visitor_count",
            label: "Visitor count",
            kind: "number",
            help: "A count only. Visitor identities are deliberately not collected.",
          },
          { name: "site_instructions", label: "Site instructions", kind: "text" },
          { name: "delays_and_reasons", label: "Delays and reasons", kind: "text" },
        ],
        submitLabel: "Submit entry",
      },
      {
        key: "ehs-create",
        title: "Report an EHS incident",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/ehs-incidents`,
        fields: [
          { name: "incident_date", label: "Incident date", kind: "date", required: true },
          {
            name: "severity",
            label: "Severity",
            kind: "select",
            required: true,
            options: ["near_miss", "minor", "major", "fatal"],
          },
          { name: "description", label: "Description", kind: "text" },
        ],
        submitLabel: "Report incident",
      },
      {
        key: "ehs-transition",
        title: "Move an EHS incident",
        scope: "none",
        path: (_s, v) => `/api/v1/ehs-incidents/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Incident ID"),
          status(["open", "corrective_action_assigned", "closed"]),
          { name: "corrective_action", label: "Corrective action", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "inspection-create",
        title: "Schedule an inspection",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/inspections`,
        fields: [
          { name: "template_id", label: "Template ID", kind: "uuid" },
          { name: "inspector_id", label: "Inspector user ID", kind: "uuid" },
          { name: "unit_id", label: "Unit ID", kind: "uuid" },
        ],
        submitLabel: "Schedule inspection",
      },
      {
        key: "inspection-complete",
        title: "Complete an inspection",
        scope: "none",
        path: (_s, v) => `/api/v1/inspections/${v["__id"] ?? ""}/complete`,
        fields: [
          targetId("Inspection ID"),
          {
            name: "result",
            label: "Result",
            kind: "select",
            required: true,
            options: ["pass", "fail", "pending"],
          },
          { name: "notes", label: "Notes", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Complete inspection",
      },
      {
        key: "snag-create",
        title: "Raise a snag",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/snags`,
        fields: [
          { name: "description", label: "Description", kind: "text", required: true },
          {
            name: "severity",
            label: "Severity",
            kind: "select",
            required: true,
            options: ["minor", "major", "critical"],
          },
          { name: "unit_id", label: "Unit ID", kind: "uuid" },
          { name: "assigned_to", label: "Assign to user ID", kind: "uuid" },
          { name: "due_date", label: "Due date", kind: "date" },
          evidence,
        ],
        submitLabel: "Raise snag",
      },
      {
        key: "snag-transition",
        title: "Move a snag",
        scope: "none",
        path: (_s, v) => `/api/v1/snags/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Snag ID"),
          status(["open", "assigned", "rectified", "verified", "closed"]),
          { name: "corrective_action", label: "Corrective action", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
    ],
  },
  {
    phase: "Phase 6",
    title: "Project controls",
    blurb: "BIM, WBS cost codes, quantities and material traceability.",
    workflows: [
      {
        key: "bim-create",
        title: "Register a BIM import",
        description: "Takes a controlled Documents UUID, never a path or URL.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/bim-imports`,
        fields: [
          { name: "source_document_id", label: "Source document ID", kind: "uuid", required: true },
        ],
        submitLabel: "Register import",
      },
      {
        key: "bim-transition",
        title: "Move a BIM import",
        scope: "none",
        path: (_s, v) => `/api/v1/bim-imports/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Import ID"),
          status(["received", "validating", "validated", "rejected", "imported"]),
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "cost-code",
        title: "Add a cost code",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/cost-codes`,
        fields: [
          { name: "code", label: "Code", kind: "text", required: true },
          { name: "description", label: "Description", kind: "text" },
          { name: "parent_cost_code_id", label: "Parent cost code ID", kind: "uuid" },
        ],
        submitLabel: "Add cost code",
      },
      {
        key: "quantity-create",
        title: "Add a quantity item",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/quantity-items`,
        fields: [
          { name: "calculated_quantity", label: "Calculated quantity", kind: "number", required: true },
          { name: "tolerance_pct", label: "Tolerance %", kind: "number" },
          { name: "cost_code_id", label: "Cost code ID", kind: "uuid" },
          { name: "work_package", label: "Work package", kind: "text" },
        ],
        submitLabel: "Add quantity",
      },
      {
        key: "quantity-verify",
        title: "Verify a quantity",
        scope: "none",
        path: (_s, v) => `/api/v1/quantity-items/${v["__id"] ?? ""}/verify`,
        fields: [
          targetId("Quantity item ID"),
          { name: "quantity", label: "Verified quantity", kind: "number", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Verify",
      },
      {
        key: "quantity-approve",
        title: "Approve a quantity",
        description: "Approval is separate from verification, and by a different person.",
        scope: "none",
        path: (_s, v) => `/api/v1/quantity-items/${v["__id"] ?? ""}/approve`,
        fields: [
          targetId("Quantity item ID"),
          { name: "quantity", label: "Approved quantity", kind: "number", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Approve",
      },
      {
        key: "material-create",
        title: "Add a material",
        scope: "none",
        path: () => `/api/v1/materials`,
        fields: [
          { name: "name", label: "Name", kind: "text", required: true },
          { name: "unit_of_measure", label: "Unit of measure", kind: "text", required: true },
          { name: "category", label: "Category", kind: "text" },
        ],
        submitLabel: "Add material",
      },
      {
        key: "receipt-create",
        title: "Record a material receipt",
        description:
          "A receipt cannot cite a purchase order belonging to another project — the database enforces that with a composite key.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/material-receipts`,
        fields: [
          { name: "material_id", label: "Material ID", kind: "uuid", required: true },
          { name: "quantity_received", label: "Quantity received", kind: "number", required: true },
          { name: "received_date", label: "Received date", kind: "date", required: true },
          { name: "purchase_order_id", label: "Purchase order ID", kind: "uuid" },
          { name: "batch_reference", label: "Batch reference", kind: "text" },
        ],
        submitLabel: "Record receipt",
      },
      {
        key: "issuance-create",
        title: "Issue material from a receipt",
        description:
          "Issuance is serialised against its receipt and refuses cumulative quantities above accepted stock.",
        scope: "none",
        path: (_s, v) => `/api/v1/material-receipts/${v["__id"] ?? ""}/issuances`,
        fields: [
          targetId("Receipt ID"),
          { name: "quantity_issued", label: "Quantity issued", kind: "number", required: true },
          { name: "issued_date", label: "Issued date", kind: "date", required: true },
          { name: "issued_to", label: "Issued to", kind: "text" },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Issue material",
      },
    ],
  },
  {
    phase: "Phase 7",
    title: "Change control",
    blurb: "Change requests, RFIs, NCRs and quantity discrepancies.",
    workflows: [
      {
        key: "change-create",
        title: "Raise a change request",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/change-requests`,
        fields: [
          { name: "description", label: "Description", kind: "text", required: true },
          { name: "schedule_impact", label: "Schedule impact", kind: "text" },
          { name: "budget_impact", label: "Budget impact", kind: "number" },
          evidence,
        ],
        submitLabel: "Raise change request",
      },
      {
        key: "change-transition",
        title: "Move a change request",
        scope: "none",
        path: (_s, v) => `/api/v1/change-requests/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Change request ID"),
          status([
            "requested",
            "feasibility_review",
            "structural_review",
            "revised_drawings",
            "quantity_impact",
            "budget_impact",
            "procurement_impact",
            "contract_impact",
            "commercial_quotation",
            "approved",
            "implemented",
            "verified",
            "closed",
            "rejected",
          ]),
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "rfi-create",
        title: "Raise an RFI",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/rfis`,
        fields: [
          { name: "question", label: "Question", kind: "text", required: true },
          { name: "routed_to", label: "Routed to user ID", kind: "uuid" },
          evidence,
        ],
        submitLabel: "Raise RFI",
      },
      {
        key: "rfi-respond",
        title: "Respond to an RFI",
        description: "Only the routed recipient may answer.",
        scope: "none",
        path: (_s, v) => `/api/v1/rfis/${v["__id"] ?? ""}/respond`,
        fields: [
          targetId("RFI ID"),
          { name: "response", label: "Response", kind: "text", required: true },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Send response",
      },
      {
        key: "rfi-transition",
        title: "Move an RFI",
        scope: "none",
        path: (_s, v) => `/api/v1/rfis/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("RFI ID"),
          status(["raised", "routed", "responded", "closed", "overdue"]),
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "ncr-create",
        title: "Raise an NCR",
        description: "An NCR may only cite an inspection belonging to the same project.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/ncrs`,
        fields: [
          {
            name: "severity",
            label: "Severity",
            kind: "select",
            required: true,
            options: ["minor", "major", "critical"],
          },
          { name: "description", label: "Description", kind: "text", required: true },
          { name: "inspection_id", label: "Inspection ID", kind: "uuid" },
          evidence,
        ],
        submitLabel: "Raise NCR",
      },
      {
        key: "ncr-transition",
        title: "Move an NCR",
        description: "Closure requires a reinspection.",
        scope: "none",
        path: (_s, v) => `/api/v1/ncrs/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("NCR ID"),
          status(["raised", "corrective_action_assigned", "reinspection_scheduled", "closed"]),
          { name: "corrective_action", label: "Corrective action", kind: "text" },
          { name: "reinspection_id", label: "Reinspection ID", kind: "uuid" },
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
      {
        key: "discrepancy-create",
        title: "Open a quantity discrepancy case",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/discrepancy-cases`,
        fields: [
          { name: "quantity_item_id", label: "Quantity item ID", kind: "uuid", required: true },
          { name: "description", label: "Description", kind: "text" },
          evidence,
        ],
        submitLabel: "Open case",
      },
      {
        key: "discrepancy-transition",
        title: "Move a discrepancy case",
        scope: "none",
        path: (_s, v) => `/api/v1/discrepancy-cases/${v["__id"] ?? ""}/transition`,
        fields: [
          targetId("Case ID"),
          status([
            "open",
            "explanation_provided",
            "engineering_review",
            "owner_approval_required",
            "resolved",
          ]),
          { name: "proposed_resolution", label: "Proposed resolution", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Apply transition",
      },
    ],
  },
  {
    phase: "Phase 8",
    title: "Customer lifecycle",
    blurb: "Bookings, payment plans, collections, registration and possession.",
    workflows: [
      {
        key: "booking-create",
        title: "Create a booking",
        description:
          "A unit cannot carry two active bookings; the database refuses the second outright.",
        scope: "project",
        path: (s) => `/api/v1/projects/${s.project}/bookings`,
        fields: [
          { name: "customer_id", label: "Customer ID", kind: "uuid", required: true },
          { name: "unit_id", label: "Unit ID", kind: "uuid", required: true },
          { name: "booking_date", label: "Booking date", kind: "date", required: true },
          { name: "booking_document_id", label: "Booking document ID", kind: "uuid" },
        ],
        submitLabel: "Create booking",
      },
      {
        key: "payment-plan",
        title: "Add a payment plan",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/payment-plans`,
        fields: [
          targetId("Booking ID"),
          { name: "plan_name", label: "Plan name", kind: "text" },
          { name: "total_amount", label: "Total amount", kind: "number", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Add plan",
      },
      {
        key: "installment",
        title: "Add an installment",
        scope: "none",
        path: (_s, v) => `/api/v1/payment-plans/${v["__id"] ?? ""}/installments`,
        fields: [
          targetId("Payment plan ID"),
          { name: "due_date", label: "Due date", kind: "date", required: true },
          { name: "amount", label: "Amount", kind: "number", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Add installment",
      },
      {
        key: "collection",
        title: "Record a collection",
        description: "Reference fields are operational metadata only — never bank credentials.",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/collections`,
        fields: [
          targetId("Booking ID"),
          { name: "amount", label: "Amount", kind: "number", required: true },
          { name: "received_date", label: "Received date", kind: "date", required: true },
          { name: "mode", label: "Mode", kind: "text" },
          { name: "reference_number", label: "Reference number", kind: "text" },
          { name: "installment_id", label: "Installment ID", kind: "uuid" },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Record collection",
      },
      {
        key: "collection-allocate",
        title: "Allocate a collection",
        description: "Over-allocation against an installment is refused.",
        scope: "none",
        path: (_s, v) => `/api/v1/collections/${v["__id"] ?? ""}/allocate`,
        fields: [targetId("Collection ID")],
        pathFields: ["__id"],
        submitLabel: "Allocate",
      },
      {
        key: "registration",
        title: "Move registration",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/registration`,
        fields: [
          targetId("Booking ID"),
          status(["pending", "scheduled", "registered", "cancelled"]),
          { name: "registration_date", label: "Registration date", kind: "date" },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Apply",
      },
      {
        key: "possession",
        title: "Move possession",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/possession`,
        fields: [
          targetId("Booking ID"),
          status(["pending", "snag_review", "handed_over"]),
          { name: "handover_date", label: "Handover date", kind: "date" },
          evidence,
        ],
        pathFields: ["__id"],
        submitLabel: "Apply",
      },
      {
        key: "executed-contract",
        title: "Link an executed contract",
        description:
          "Refused unless the contract is executed and belongs to the same customer.",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/executed-contract`,
        fields: [
          targetId("Booking ID"),
          { name: "contract_id", label: "Contract ID", kind: "uuid", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Link contract",
      },
      {
        key: "booking-cancel",
        title: "Cancel a booking",
        description: "Cancelling releases the unit for a new booking.",
        scope: "none",
        path: (_s, v) => `/api/v1/bookings/${v["__id"] ?? ""}/cancel`,
        fields: [targetId("Booking ID")],
        pathFields: ["__id"],
        submitLabel: "Cancel booking",
      },
    ],
  },
  {
    phase: "Phase 9",
    title: "Tally reconciliation",
    blurb:
      "Tally stays the statutory book of record — Atlas can neither post nor amend a voucher.",
    workflows: [
      {
        key: "tally-import",
        title: "Register a Tally export",
        description: "The export itself stays in a restricted Documents record.",
        scope: "entity",
        path: (s) => `/api/v1/legal-entities/${s.entity}/tally-imports`,
        fields: [
          { name: "source_document_id", label: "Source document ID", kind: "uuid", required: true },
          {
            name: "content_sha256",
            label: "SHA-256 of the export",
            kind: "text",
            required: true,
            help: "64 lowercase hex characters; provides provenance for the batch.",
          },
          { name: "period_start", label: "Period start", kind: "date" },
          { name: "period_end", label: "Period end", kind: "date" },
        ],
        submitLabel: "Register export",
      },
      {
        key: "tally-validate",
        title: "Validate an import batch",
        scope: "none",
        path: (_s, v) => `/api/v1/tally-imports/${v["__id"] ?? ""}/validate`,
        fields: [targetId("Batch ID")],
        pathFields: ["__id"],
        submitLabel: "Validate",
      },
      {
        key: "tally-voucher",
        title: "Ingest a normalised voucher",
        scope: "none",
        path: (_s, v) => `/api/v1/tally-imports/${v["__id"] ?? ""}/vouchers`,
        fields: [
          targetId("Batch ID"),
          { name: "external_id", label: "External ID", kind: "text", required: true },
          { name: "voucher_type", label: "Voucher type", kind: "text", required: true },
          { name: "voucher_number", label: "Voucher number", kind: "text", required: true },
          { name: "voucher_date", label: "Voucher date", kind: "date", required: true },
          { name: "amount", label: "Amount", kind: "number", required: true },
          { name: "ledger_reference", label: "Ledger reference", kind: "text", required: true },
        ],
        pathFields: ["__id"],
        submitLabel: "Ingest voucher",
      },
      {
        key: "reconciliation-create",
        title: "Raise a reconciliation case",
        description: "The same fact cannot be raised twice, NULL voucher included.",
        scope: "entity",
        path: (s) => `/api/v1/legal-entities/${s.entity}/reconciliations`,
        fields: [
          { name: "erp_reference_type", label: "ERP reference type", kind: "text", required: true },
          { name: "erp_reference_id", label: "ERP reference ID", kind: "uuid", required: true },
          {
            name: "discrepancy_type",
            label: "Discrepancy type",
            kind: "select",
            required: true,
            options: [
              "missing_in_tally",
              "missing_in_erp",
              "amount_mismatch",
              "wrong_entity",
              "wrong_project",
              "duplicate_voucher",
              "unallocated_receipt",
              "schedule_not_updated",
              "obligation_still_open",
            ],
          },
          { name: "erp_amount", label: "ERP amount", kind: "number" },
          { name: "tally_amount", label: "Tally amount", kind: "number" },
        ],
        submitLabel: "Raise case",
      },
      {
        key: "reconciliation-review",
        title: "Review a reconciliation case",
        scope: "none",
        path: (_s, v) => `/api/v1/reconciliations/${v["__id"] ?? ""}/review`,
        fields: [
          targetId("Reconciliation ID"),
          status(["open", "under_review", "reconciled", "accepted_exception"]),
          { name: "resolution_code", label: "Resolution code", kind: "text" },
          { name: "resolution_note", label: "Resolution note", kind: "text" },
        ],
        pathFields: ["__id"],
        submitLabel: "Record review",
      },
    ],
  },
];
