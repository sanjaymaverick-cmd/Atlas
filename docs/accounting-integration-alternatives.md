# Open-source accounting alternatives for Atlas

**Decision status:** research recommendation, not an implementation decision.
**Reviewed:** 24 August 2026.
**Scope:** self-hosted accounting ledgers that Atlas could integrate with instead of paid Tally. This review uses vendor/project primary sources. “Open source” describes the software licence, not the cost of hosting, implementation, support, statutory gateways, or upgrades.

## Executive recommendation

1. **ERPNext + India Compliance — preferred proof of concept.** It has the best combination of genuine open-source licensing, accounting/procurement/projects, India GST/e-invoice/e-waybill coverage, and a usable HTTP API. Run it as a separate service; do not rebuild Atlas on Frappe.
2. **Tryton — preferred technically conservative fallback.** Python, PostgreSQL, modular double-entry accounting and RPC/REST clients align well with Atlas. Its decisive weakness is the absence of officially documented India GST/e-invoice localization; Atlas would inherit a substantial statutory adapter and validation burden.
3. **Odoo Community — evaluate only with a licence/edition feature matrix.** It is mature and has strong India localization, but official documentation warns that important features can trigger paid-plan/Enterprise requirements. A Community-only pilot must prove that every required accounting, reporting, multi-company, API and India module is LGPL-compatible and actually installable without Enterprise code.
4. **LedgerSMB — accounting-first fallback.** It is genuinely open source and PostgreSQL-native with good audit-control concepts, but its v0 web API is explicitly not stable and there is no official India compliance package.

Do **not** shortlist Akaunting as “fully free/open source” without accepting its Business Source License and paid-app split. Do not use GnuCash as the shared operational ledger: it is excellent desktop accounting software, but not a production multi-user ERP integration target. Dolibarr is viable for simpler businesses, but core multi-company requires an external module and official India compliance is not evident.

## Architectural boundary for every candidate

Atlas must remain the control plane and system of record for identity, authorization, project/evidence workflows, approvals, and its hash-chained audit. The accounting system is a separately deployed ledger bounded by a provider-neutral adapter:

`Atlas approved business event → transactional outbox → idempotent adapter → accounting API → immutable sync receipt/reconciliation → Atlas audit chain`

Never share database schemas or write directly into the accounting product’s tables. Use a least-privilege integration identity, outbound allow-listing, TLS, secret-manager references, idempotency keys, bounded retries, dead-letter handling, mapping versions, and reconciliation. The accounting product owns posted journals and statutory accounting outputs; Atlas owns approval authority and evidence. Corrections should be reversal/credit workflows, not silent mutation. Product audit logs supplement rather than replace Atlas’s audit chain.

## Comparison

| Product | Licence / free-edition reality | Runtime and integration surface | Accounting/entity capability | India and construction fit | Atlas risk assessment |
|---|---|---|---|---|---|
| **ERPNext** | ERPNext is **GPL-3.0** and describes itself as 100% open source ([official repository](https://github.com/frappe/erpnext)). Frappe is separately licensed; self-hosting is supported. Hosting/support and statutory service providers may cost money. | Python/Frappe; current deployments conventionally use MariaDB. Frappe generates REST CRUD for DocTypes plus whitelisted RPC methods; token calls are attributed to a user and roles apply ([REST API](https://docs.frappe.io/framework/user/en/api/rest)). | Integrated accounting, projects, procurement, inventory and assets; company/currency fields are first-class. Strongest functional fit for construction job-cost handoff. | Official ERPNext docs describe the separate **India Compliance** app for GST, GSTIN, HSN/SAC, returns, e-invoice, e-waybill, TDS and TCS ([India Compliance](https://docs.frappe.io/erpnext/v12/user/manual/en/regional/india/setup-e-invoicing)). Verify the current app licence/version matrix and any GSP fees in the pilot. | Best functional match. Risks: MariaDB adds another database stack; flexible DocTypes can encourage over-coupling; upgrades and India Compliance compatibility need rehearsal; GPL review is needed if distributing modifications. |
| **Tryton** | “100% Open Source”; server/modules are generally **GPL-3.0** ([official repository](https://github.com/tryton/tryton)). No official Community/Enterprise feature gate. | Python; PostgreSQL is a normal production backend. Server supports JSON-RPC and XML-RPC ([RPC docs](https://docs.tryton.org/latest/server/topics/rpc.html)); official documentation also lists scripting and REST clients ([documentation index](https://docs.tryton.org/latest/)). | The account module provides basic double-entry accounting ([account module](https://docs.tryton.org/7.8/modules-account/index.html)); modules cover projects, purchases, stock, production and quality. Company/currency are foundational. | Good modular fit for construction; no official India GST/e-invoice localization found in current project documentation. That absence must be treated as a blocker until a maintained, legally reviewed module is demonstrated. | Excellent code/runtime alignment and clean modularity. Risks: statutory implementation burden, version-coupled modules, smaller India implementer ecosystem, RPC semantics rather than a narrow stable business API. |
| **Odoo Community** | The public Community repository is **LGPL-3.0** ([licence](https://github.com/odoo/odoo/blob/19.0/LICENSE)); Odoo also sells Enterprise modules/services. Official material distinguishes Community from Enterprise and lists Accounting among Enterprise extras ([official culture document](https://www.odoo.com/web/content/31413934)). | Python/PostgreSQL. Odoo 19 exposes JSON-2 with API keys, dedicated bot users, record rules and access logs ([external API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)). API/edition availability must be confirmed for the deployed Community version. | Official accounting docs cover double-entry, multi-company and multi-currency ([accounting](https://www.odoo.com/documentation/19.0/applications/finance/accounting.html)). Broad projects, purchase, inventory and analytic accounting suit construction. | Official India localization lists `l10n_in`, e-invoice, e-waybill and GST reporting modules and a GSP configuration ([India localization](https://www.odoo.com/documentation/19.0/applications/finance/fiscal_localizations/india.html)). Confirm which modules/features are Community LGPL versus Enterprise/licensed dependencies. | Very capable, but highest edition-surprise risk. Official docs warn multi-company can trigger a paid Custom plan in hosted offerings ([multi-company](https://www.odoo.com/documentation/19.0/applications/general/companies/multi_company.html)). Maintain an allow-list of permitted module licences and test it in CI. |
| **LedgerSMB** | **GPL-2.0**, web-based double-entry accounting/ERP ([official repository](https://github.com/ledgersmb/LedgerSMB)). No Community/Enterprise split identified. | Perl and PostgreSQL 14+. OpenAPI endpoint exists at `/erp/api/v0`, but the official book says major version zero is not stable and filtering/sorting/pagination remain incomplete ([API chapter](https://github.com/ledgersmb/ledgersmb-book/blob/master/part-customization.tex)). | Quotations, orders, invoicing, projects/timecards, inventory and purchasing. Historically one isolated PostgreSQL database per company. Audit Control is a notable accounting safeguard ([official book](https://book.ledgersmb.org/1.3/ledgersmb.pdf)). | Useful project/job-cost basics; no official India GST/e-invoice package found. | PostgreSQL alignment and accounting focus are attractive. Risks: unstable/incomplete API, Perl skills, per-company operational model, and India localization burden. |
| **Dolibarr** | **GPL-3.0-or-later** and self-hostable ([official repository](https://github.com/Dolibarr/dolibarr)). Marketplace modules can have separate terms. | PHP with MariaDB/MySQL/PostgreSQL; official repository lists REST and SOAP APIs, hooks and triggers. | Accounting, invoices, orders, stock, manufacturing and projects; multi-currency is core, but multi-company is provided by an **external module**. | Broad ERP features, but the official feature list does not establish India GST/e-invoice support. | Easier operationally than a large ERP, but external-module dependence for legal entities and uncertain India compliance weaken fit. PHP stack and marketplace upgrade/licence risk add cost. |
| **Akaunting** | Self-hosted Standard is advertised as free, but the repository is under a **Business Source License**, not an OSI-approved permissive/copyleft licence, and official plans sell higher tiers/apps ([repository](https://github.com/akaunting/akaunting), [on-premise plans](https://akaunting.com/hc/docs/getting-started/plans/on-premise-pricing-plans/)). | PHP/Laravel; cloud and on-premise. Integration features can depend on commercial apps/plan, so API entitlement needs contractual verification. | Official docs advertise double-entry, projects, multi-currency and company management ([getting started](https://akaunting.com/hc/docs/getting-started/)). Multiple companies appear tiered. | No official India GST/e-invoice capability established. | Fails the strict “genuinely open-source and predictably free” requirement. Feature/app monetization creates the same lock-in concern that motivated leaving Tally. |
| **GnuCash** | **GPL-2.0-or-later**, mature desktop accounting ([official repository](https://github.com/Gnucash/gnucash)). | C/GTK desktop application; XML and SQL storage exist, but it is not designed as a network ERP with a supported transactional REST service. | Strong double-entry and multi-currency for a person/small business; invoices and reports. Multi-company is normally separate books rather than governed legal entities. | No official India GST/e-invoice service integration or construction workflow. | Useful as an accountant-side validation/export tool, not the authoritative shared ledger. Direct database automation would be fragile and unsupported. |

## Ranked proof-of-concept scorecard

Score is directional (5 best) and must be replaced by a scripted pilot using Atlas fixtures.

| Candidate | Open/free certainty | Atlas API fit | Accounting breadth | India compliance | Construction/projects | Upgrade operability | Total / 30 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ERPNext + India Compliance | 5 | 4 | 5 | 5 | 5 | 3 | **27** |
| Odoo Community (verified modules only) | 3 | 4 | 5 | 5 | 5 | 2 | **24** |
| Tryton | 5 | 4 | 4 | 1 | 4 | 4 | **22** |
| LedgerSMB | 5 | 2 | 4 | 1 | 3 | 3 | **18** |
| Dolibarr | 5 | 3 | 3 | 1 | 3 | 3 | **18** |
| Akaunting | 1 | 2 | 3 | 1 | 2 | 2 | **11** |
| GnuCash | 5 | 1 | 3 | 1 | 1 | 3 | **14** |

## Tally migration assessment

### What can be exported legitimately and technically

Tally’s official help documents customer-controlled export of accounting/inventory masters, masters with balances, all or selected vouchers (optionally including dependent masters), reports and GST returns to XML, JSON, Excel and other formats ([Tally export guide](https://help.tallysolutions.com/data-management/export-data-in-tally/)). It also documents full company transfer by exporting masters first and transactions second, and checking chart-of-accounts and transaction reports after import ([import FAQ](https://help.tallysolutions.com/import-data-faq/)). Those supported exports—not reverse-engineering Tally’s binary storage—should be the migration source.

In general, moving a customer’s own business records is ordinary data portability. That does **not** authorize copying, modifying, redistributing or reverse-engineering proprietary Tally program code, TDL components, schemas, licences, or protected documentation. Contract/licence terms and applicable Indian law must be reviewed by counsel for the actual deployment. Retain the original licensed Tally environment or a legally usable archival export for the statutory retention period; preserve GST/e-invoice acknowledgements and source documents; obtain accountant/tax-adviser sign-off before cutover.

### Required migration pipeline

1. Freeze a cutover timestamp and take a verified Tally backup.
2. Export masters, opening balances, full voucher history, inventory vouchers, cost centres, GST reports and source attachments using supported functions. Produce control totals and file hashes; never alter originals.
3. Land exports in an access-controlled, encrypted migration store. Parse into a versioned neutral model; retain Tally GUID/voucher identifiers as external references.
4. Load masters before transactions. Use product-supported import/API paths, never direct database inserts.
5. Reconcile by legal entity, fiscal year, ledger, voucher type, GSTIN, tax code, currency, cost centre/project, item/warehouse and bank account.
6. Prove opening and closing trial balances, P&L, balance sheet, receivables/payables ageing, inventory quantity/value, GST returns, e-invoice IRN/acknowledgements, and bank reconciliation against signed Tally reports.
7. Record exceptions and approvals in Atlas’s hash-chained audit. Run parallel books for an owner/accountant-approved period; make corrections through explicit reversal/adjustment entries.

### Platform-by-platform difficulty

| Target | Supported target ingestion | Masters / opening balances | Full voucher history | GST/e-invoice | Inventory / cost centres / projects | Bank, attachments, audit | Overall |
|---|---|---|---|---|---|---|---|
| **ERPNext** | Frappe REST CRUD/RPC, file upload, and a mapping-oriented Data Migration Tool ([official migration tool](https://docs.frappe.io/framework/user/en/guides/data/using-data-migration-tool)). | **Medium:** natural DocTypes, but charts, parties, tax templates and opening entries require ordered mapping. | **Medium-high:** translate each voucher into submitted ERPNext documents/journal entries; preserve external IDs and reversals. | **Medium:** best official target coverage through India Compliance, but IRN/acknowledgement fields and historical filing status need field-level proof. | **Medium:** strong stock, warehouses, dimensions/projects; Tally cost-category semantics need mapping. | **High-risk areas:** bank reconciliation state and attachments need separate imports; source Tally edit history cannot become native ERPNext history—retain it as evidence and Atlas hashes. | **Best candidate; medium-high project.** |
| **Odoo Community** | Official UI imports master data in dependency order ([getting started](https://www.odoo.com/documentation/19.0/applications/finance/accounting/get_started.html)); JSON-2 API is available in current official docs. | **Medium:** robust models, but edition/module-qualified field maps are essential. | **High:** posted move/invoice constraints, sequences and immutable states require carefully ordered API loads. | **Medium only if Community module audit passes:** official localization is broad, but verify licence/dependencies and GSP behavior. | **Medium:** strong inventory/analytic/project concepts, with semantic mapping effort. | **High-risk areas:** bank reconciliation models, documents and source audit history. Keep immutable export evidence in Atlas; do not fabricate Odoo create/write metadata. | **Capable, but edition/licence uncertainty raises risk.** |
| **Tryton** | Supported JSON/XML-RPC and official scripting/REST clients. | **Medium:** modular models and PostgreSQL help, but templates/configuration precede balances. | **High:** application workflows and period controls must be respected through RPC. | **Very high:** no verified official India layer; statutory history may remain external evidence and future compliance would require owned localization. | **Medium:** official stock/project/purchase modules, but Tally cost-centre mappings are custom. | **High:** bespoke reconciliation, attachment and audit-evidence import. | **Technically clean; India gap makes migration high-risk.** |
| **LedgerSMB** | OpenAPI v0 service; official API is not stable/complete. CSV/templates are available for outputs, but target bulk-import coverage must be proven. | **Medium:** accounting model fits, with one database/dataset per company. | **Very high:** API gaps likely require supported loaders or staged/manual work; direct SQL is prohibited. | **Very high:** no official India package verified. | **Medium-high:** projects/inventory exist, but mappings and APIs are less mature. | **High:** audit control is useful, but Tally history remains external evidence; bank/attachment migration needs a pilot. | **Accounting-solid, integration-heavy.** |
| **Dolibarr** | Official REST/SOAP API and module hooks; validate bulk import coverage in a pilot. | **Medium:** common masters straightforward; external multi-company module complicates entity setup. | **High:** voucher-to-ledger semantics and completeness need custom adapter work. | **Very high:** no official India localization established. | **Medium:** inventory/projects available; cost dimensions require mapping. | **High:** bank, attachments and historic audit evidence require separate work. | **Usable only for simpler scope.** |

GnuCash and Akaunting are excluded from migration prototyping for the reasons above. A one-time CSV/XML import into GnuCash may help an accountant independently compare balances, but it should not be the operational cutover target.

### Data-domain caveats

- **Masters:** retain original names and IDs but introduce stable Atlas mapping IDs. Deduplicate PAN/GSTIN and party records only through an approved exception workflow.
- **Opening balances:** use either full-history migration or opening balances at a signed cutover—not both in a way that double counts. Tie AR/AP openings to parties and invoices.
- **Voucher history:** preserve voucher type/number/date, narration, references, bill allocations, currency/rate, debit/credit lines, cancellations and reversals. Compare counts and debit=credit totals per period.
- **GST/e-invoice:** preserve GSTIN, place of supply, HSN/SAC, tax components, reverse charge, invoice type, IRN, acknowledgement number/date, signed QR/e-waybill references and filing period. Validate with a practising Indian accountant and current GSTN/GSP rules.
- **Inventory:** reconcile opening and closing quantity and value per item, batch/serial, godown/warehouse and valuation method; accounting value alone is insufficient.
- **Cost centres/projects:** Tally cost centres/categories do not map automatically to Atlas projects or target analytic dimensions. Require explicit effective-dated many-to-one/one-to-many mapping approval.
- **Bank reconciliation:** migrate statements and cleared dates only where the target officially supports it; otherwise retain signed bank rec reports and re-reconcile outstanding items in the target.
- **Attachments:** Tally’s generic data export documentation does not prove complete binary attachment export. Inventory attachment locations separately, hash each file, classify access/retention, and link via Atlas evidence IDs.
- **Audit trail:** never claim imported records reproduce Tally Edit Log/audit metadata. Retain signed reports, original exports, hashes, extraction logs and mapping versions; Atlas records migration decisions and reconciliation approvals.

## Proof-of-concept acceptance gates

Use a disposable deployment and synthetic Indian construction fixtures only. Pilot ERPNext first and Odoo Community second only if ERPNext fails a gate.

- The exact versions and licences of core, localization and every dependency are captured; no Enterprise/non-free module is installed unintentionally.
- Separate legal entities and currencies cannot leak records across integration credentials.
- Atlas can idempotently create and query parties, projects/cost dimensions, sales/purchase documents, collections, journal entries and reversals through supported APIs.
- Posted accounting data cannot be silently overwritten; reversal and lock-period behavior is demonstrated.
- GST split, HSN/SAC, place of supply, TDS/TCS, e-invoice and e-waybill paths work in a non-production/test environment without real credentials.
- A simulated Tally export migrates masters, two fiscal years of vouchers, inventory and cost centres; all control totals reconcile and rerunning creates no duplicates.
- API secrets are externally managed and rotatable; least-privilege service accounts and access logs are proven.
- Upgrade rehearsal preserves mappings and passes contract tests; backup restore and disaster recovery are demonstrated.
- Atlas stores only necessary external IDs/statuses and hashes, not replicated sensitive ledger payloads or credentials.

## Owner decisions before implementation

- Select ERPNext as the Phase 9 proof-of-concept target, or authorize the Odoo Community edition/licence audit first.
- Confirm whether the accounting product or Atlas is authoritative for customers/suppliers, projects/cost centres, invoices, collections and tax classifications.
- Approve India Compliance/GSP operating costs and confirm statutory fitness with a chartered accountant; “open-source” cannot substitute for professional compliance validation.
- Approve GPL/LGPL/BSL obligations with counsel, particularly if modified software is distributed or offered to third parties.
- Approve per-entity integration identities, data minimization, retention, backup, data residency, breach response and administrator-access policy.
- Approve cutover date, historic depth, parallel-run period, reconciliation tolerances and archival access to Tally.
- Decide whether attachments remain solely in Atlas evidence storage or are copied into the ledger, and document the resulting privacy/retention boundary.
