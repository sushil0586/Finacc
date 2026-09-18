# Advanced GST Compliance Launch Readiness Plan

Date: 17 Sep 2026

## Goal

Make GST compliance launch-ready end to end: outward supplies, inward/ITC matching, GSTR-1/3B reconciliation, GST portal workflow, e-invoice/e-way bill lifecycle, amendments, exceptions, compliance calendar, and stage/browser certification.

This is not a greenfield module. The product already has several strong GST pieces. The goal is to connect them into one accountant-friendly compliance workflow with clear evidence, not duplicate logic.

## Current Foundation

Already present in the backend:

- GSTR-1 modular report stack under `reports/gstr1`.
- GSTR-3B services, views, exporters, serializers, and tests under `reports/gstr3b`.
- GSTR-9 scaffold under `reports/gstr9`.
- GST portal workflow/profile models, services, WhiteBooks integration, and tests under `reports/gst_portal`.
- GST reconciliation app with imported returns, GSTR-2B importer, matching engine, item workflow, source document providers, dashboard service, and runtime indexes.
- GST exception dashboard and sales GSTIN services.
- Sales compliance services for e-invoice/e-way bill, provider integrations, artifacts, audit, and error catalog.
- Purchase statutory and GSTR-2B review services.
- GST-TDS configuration and compliance center.
- TCS/TDS compliance infrastructure in withholding/reporting areas.
- Existing GST docs and runbooks under `docs/gst`, `docs/reports`, and `docs/qa`.

Already present in the frontend:

- GST report pages, GSTR-3B page, GSTR-9 page.
- GSTR-1/GSTR-3B reconciliation page.
- GST exception dashboard.
- GST reconciliation dashboard/run list/run detail/item grid/bulk actions/manual match/detail drawer.
- Sales invoice compliance workspace and actions.
- Purchase compliance/statutory screens.
- GST-TDS compliance center and config.
- TCS compliance/config/return screens.

## Existing GST Surface Review Before Umbrella Build

Status: required before starting the umbrella implementation.

The GST Compliance Center must be a connector layer over existing working screens. It must not duplicate or replace them until a workflow is explicitly retired.

### Canonical Frontend Screens To Review

Primary GST and statutory screens:

- `/gstreport` - GSTR-1 readiness, section/table review, validation, export, GST portal controls.
- `/gstr3breport` - GSTR-3B summary, validation, export, GST portal controls.
- `/reports/gstr9`, `/gstr9report`, `/reports/statutory/gstr9` - GSTR-9 annual return, freeze, filing, export.
- `/reports/compliance/gstr1-vs-gstr3b` - GSTR-1 vs GSTR-3B reconciliation and output GST ledger check.
- `/reports/compliance/gst-exception-dashboard` - GST anomalies, mismatch queues, and exception review.
- `/gst-reconciliation` - GST reconciliation dashboard for imported returns and reviewer queue.
- `/gst-reconciliation/runs/:runId` - reconciliation run detail, item grid, manual match, bulk actions, supplier analytics.
- `/reports/gst-tds` and `/tax/gst-tds-reports` - GST-TDS compliance center.
- `/gstdsconfig` - GST-TDS configuration.
- `/reports/tcs`, `/tax/tcs-reports`, `/tcsledgerreport`, `/tcsfilingpack` - TCS compliance family.
- Sales invoice compliance workspace - e-invoice/e-way lifecycle, artifacts, provider errors, retries, cancellation.
- Purchase statutory and purchase GSTR-2B review screens - purchase ITC, 2B batches, matching status, statutory review.

### Canonical Backend APIs / Services To Review

Existing report and filing APIs:

- `reports/gstr1/*` - GSTR-1 meta, summary, readiness, section, table, validations, export, invoice detail.
- `reports/gstr3b/*` - GSTR-3B meta, summary, validations, export.
- `reports/gstr9/*` - GSTR-9 meta, summary, table, validations, export, freeze, filing prepare/submit/status.
- `reports/gst-reconciliation/summary/` and `reports/gst-reconciliation/export/` - GSTR-1 vs GSTR-3B reconciliation.
- `reports/gst-exception-dashboard/*` - GST exception dashboard and export.
- `reports/gst-portal/*` - GST portal profile, OTP/session, prepare/save/status/proceed/EVC/poll flows.
- `gst-reconciliation/*` - imported returns, GSTR-2B import, run lifecycle, matching, reviewer queue, item actions, source document lookup.
- `purchase/gstr2b/*` and purchase statutory services - 2B import batches, rows, matching, review decisions.
- Sales compliance APIs/services - e-invoice/e-way generation, cancellation, lookup, artifacts, provider credentials, audit logs.

### Umbrella Ownership Rule

The umbrella GST Compliance Center should:

- Reuse existing APIs for status and drilldowns wherever possible.
- Add only lightweight summary/aggregation APIs where the UI needs one combined view.
- Deep link into canonical existing screens for detailed work.
- Keep existing route permissions intact.
- Preserve current GSTR-1, GSTR-3B, GSTR-9, reconciliation, exception, sales compliance, purchase statutory, GST-TDS, and TCS workflows.
- Treat missing setup as visible readiness warnings, not hard crashes.

### First Review Checklist

Before implementing the umbrella screen:

- Open `/gstreport`, `/gstr3breport`, `/reports/gstr9`, `/reports/compliance/gstr1-vs-gstr3b`, `/reports/compliance/gst-exception-dashboard`, `/gst-reconciliation`, `/reports/gst-tds`, and `/reports/tcs`.
- Confirm each page's active filters: entity, FY, subentity, GSTIN/period/date range.
- Confirm export buttons, smart filters, tabs, empty states, and drilldowns.
- Confirm which screens already include GST portal actions and which only provide offline export.
- Confirm GSTR-2B/ITC workflow entry points from purchase statutory and GST reconciliation.
- Confirm sales compliance workspace covers e-invoice/e-way status, action flags, artifacts, and retry/cancel states.
- Record any duplicated page responsibility before creating new UI.

## Pre-Build Gap Audit

Status: documented before starting the umbrella implementation on 17 Sep 2026.

### What Is Already Strong

- GST is not starting from zero. GSTR-1, GSTR-3B, GSTR-9, GST portal filing, GSTR-1 vs GSTR-3B reconciliation, GST exception dashboard, GSTR-2B matching, sales compliance, purchase statutory, GST-TDS, and TCS surfaces already exist.
- Backend APIs already expose canonical GSTR-1, GSTR-3B, GST portal, reconciliation, exception, and GSTR-9 endpoints.
- Frontend routes already expose the major accountant-facing pages:
  - `/gstreport`
  - `/gstr3breport`
  - `/gstr9report`
  - `/reports/gstr9`
  - `/reports/statutory/gstr9`
  - `/reports/compliance/gstr1-vs-gstr3b`
  - `/reports/compliance/gst-exception-dashboard`
  - `/gst-reconciliation`
  - `/gst-reconciliation/runs/:runId`
  - `/reports/gst-tds`
  - `/reports/tcs`
- Existing report endpoints already follow the scope pattern of entity, entity financial year, subentity, period/date range, permission, and subscription enforcement.
- Output GST ledger reconciliation has been added to the GSTR-1 vs GSTR-3B flow and now reports static-account setup warnings instead of failing silently.

### Gap Matrix

| Area | Current State | Gap | Launch Requirement | Priority |
| --- | --- | --- | --- | --- |
| GST umbrella cockpit | Multiple strong pages exist, but each page is reached separately. | No single GST Compliance Center that tells the accountant what is ready, blocked, filed, overdue, or needs review. | Add a lightweight aggregation page/API with readiness cards and deep links to existing canonical screens. | P0 |
| Common GST scope | Existing pages use entity, FY, subentity, month/year, from/to date, and sometimes GSTIN differently. | No single normalized GST compliance scope contract across all GST screens. | Define one scope object: entity, entityfinid, subentity, GSTIN, return period, from date, to date, return type. | P0 |
| Return period lifecycle | GST portal and GSTR-9 filing/freeze pieces exist. | No unified monthly/annual period lifecycle across GSTR-1, GSTR-3B, 2B/ITC, exceptions, and filing status. | Track each GSTIN/period as Open, Prepared, Reviewed, Frozen, Filed, Amendment Needed, or Reopened. | P0 |
| GSTR-1/GSTR-3B evidence | Reconciliation and output GST ledger tie-out exist. | Evidence is still page-local; export pack is not a single filing-ready bundle. | One evidence pack containing GSTR-1, GSTR-3B, reconciliation rows, ledger tie-out, warnings, and export metadata. | P0 |
| Input GST ledger reconciliation | GSTR-2B matching and purchase statutory pieces exist. | ITC is not yet tied as strongly to input GST ledgers as outward tax is tied to output GST ledgers. | Add input CGST/SGST/IGST/CESS ledger tie-out against ITC claimed/deferred/blocked. | P0 |
| GSTR-2B / IMS accountant workspace | GST reconciliation dashboard/run details and purchase GSTR-2B models/services exist. | Accountant flow is not fully presented as one simple ITC review journey from import to match to decision to 3B impact. | One guided ITC workspace: import/download, run match, review exceptions, accept/defer/reject, post decision evidence. | P0 |
| Exception ownership | GST exception dashboard aggregates warning rows and reconciliation rows. | Exceptions are not yet treated as assignable compliance tasks with owner, due date, comments, closure, and history. | Add task/owner/status layer or connect exceptions to a reusable task model. | P1 |
| E-invoice/e-way period visibility | Sales invoice compliance workspace handles invoice-level actions and states. | GST cockpit does not summarize IRN/EWB generated, failed, cancelled, expired, retry-ready, or not-applicable counts by period/GSTIN. | Add period-level e-invoice/e-way health card and drilldown into sales compliance/source invoice. | P1 |
| GST portal operations | GST portal prepare/save/status/EVC/poll/profile endpoints exist. | Portal workflow is not consistently shown as one filing journey from readiness to portal status to filed evidence. | Expose portal readiness, session/profile state, last status poll, provider error, and filing evidence in the umbrella. | P1 |
| Amendments | GSTR reports and filing pieces exist. | Previous-period amendments are not clearly modeled as a first-class workflow across GSTR-1, GSTR-3B, and source documents. | Amendment queue with source document, original period, amendment period, tax delta, filing impact, and audit. | P1 |
| Compliance calendar | Due dates are mentioned in product goals. | No verified unified GST due-date/calendar center for GSTR-1, 3B, 7, 9, e-way expiry, and notice deadlines. | Calendar by GSTIN/return type with overdue, upcoming, and blocked states. | P1 |
| Notices and department workflow | Not currently visible as a connected GST surface in the reviewed list. | Notices, replies, attachments, assignment, and closure are not part of the umbrella flow. | Add notice/task register, ideally after cockpit and ITC launch readiness. | P2 |
| RBAC and menus | Routes have individual permission requirements. | New umbrella route and deep links need permission mapping without weakening existing route access. | Add route permission matrix for view, export, import, match, freeze, file, amend, and notice actions. | P0 |
| Browser certification | Existing Angular specs and focused Playwright tests exist for several GST pages. | Umbrella journey and full period workflow are not yet covered end to end in browser automation. | Add Playwright tests for cockpit, GSTR-1/3B drilldown, ITC run review, exception flow, exports, RBAC, and mobile/tablet smoke. | P0 |
| WhiteBooks/provider dependency | WhiteBooks integration exists for GST portal and sales compliance areas. | Need final contract map of which advanced GST actions require live provider calls and which can run from local/imported data. | Document provider action matrix: local-only, sandbox-capable, live-only, credential-required, OTP-required. | P1 |

### Product Shape To Build

The umbrella should be a command center, not another report clone.

Recommended first screen:

- Top scope bar: entity, GSTIN, financial year, return period, subentity, status.
- Readiness strip: GSTR-1, GSTR-3B, ITC/2B, e-invoice/e-way, exceptions, portal, filing pack.
- Work queue: blocked items first, then needs review, then ready.
- Action cards:
  - Prepare GSTR-1
  - Review 3B
  - Match ITC
  - Resolve exceptions
  - Check e-invoice/e-way
  - Build filing evidence pack
  - Open GST portal workflow
- Every card must deep link to the current canonical page instead of recreating detailed tables.

### Implementation Guardrails

- Do not replace existing GST pages in the first release.
- Do not duplicate existing report calculations in the frontend.
- Add a backend aggregation service only for summary/readiness/state; use existing services for detailed rows.
- Treat setup issues as readiness warnings:
  - missing GSTIN
  - missing GST portal profile
  - missing static tax ledger mapping
  - missing WhiteBooks credentials
  - missing route permission
  - missing financial year/subentity scope
- Keep exports and drilldowns permission-aware.
- Preserve current stage/live behavior for GSTR-1, GSTR-3B, GSTR-9, GST reconciliation, GST exception dashboard, sales compliance, purchase statutory, GST-TDS, and TCS.

### Immediate Implementation Order

1. Define the GST compliance scope and status contract.
2. Add backend aggregation endpoint for the umbrella readiness snapshot.
3. Build the frontend GST Compliance Center shell using existing application UI patterns.
4. Add deep links to canonical pages with scope carried forward.
5. Add input GST ledger reconciliation to the ITC/2B side.
6. Add Playwright coverage for the accountant journey and permission restrictions.

## Execution Phase Breakdown

This is the working sequence for development and certification. Each phase must leave the product usable on its own; no phase should break the existing standalone GST pages.

### Phase A: Foundation Contract And Navigation

Purpose: create the common language for GST compliance before adding new UI.

Build scope:

- Define `GstComplianceScope`: entity, entityfinid, subentity, GSTIN, return type, return period, from date, to date.
- Define common status values: Not Configured, Ready, Needs Review, Blocked, Prepared, Frozen, Filed, Amendment Needed, Overdue.
- Define canonical deep-link contract for GSTR-1, GSTR-3B, GSTR-9, 2B/ITC, exception dashboard, sales compliance, GST-TDS, and TCS.
- Add route/menu permission plan for the future GST Compliance Center without weakening current GST routes.

Backend work:

- Add scope/status helper module for GST compliance aggregation.
- Add unit tests for period/date/GSTIN scope normalization.
- Add no behavior change to existing report endpoints.

Frontend work:

- Add route placeholder/menu metadata only if needed.
- Add shared GST compliance models/types.

Certification gate:

- Existing GST pages continue to open.
- Existing GST tests remain green.
- No duplicate calculation logic is introduced.

Phase A implementation status on 17 Sep 2026:

- Backend contract added in `reports.gst_compliance`: normalized `GstComplianceScope`, shared status vocabulary, and canonical deep-link builder.
- Frontend contract added in `src/app/model/gst-compliance.ts`: shared statuses, routes, permissions, features, access modes, and query-param builder.
- Route contract tests added so current GST routes cannot drift away from the shared contract unnoticed.
- Browser certification tests added for existing GST report, reconciliation, and exception routes.
- No existing GST report endpoint behavior is intentionally changed in this phase.

Phase A definition of done:

- Backend contract tests pass for GSTIN, period, date, FY, and deep-link normalization.
- Angular contract and route tests pass.
- Playwright opens the current canonical GST workspaces without unauthorized/login redirects.
- Targeted existing GST Playwright suites pass the Phase A route contract checks.

Phase A QA evidence:

- Backend: `./venv/bin/python manage.py test reports.tests_gst_compliance_contracts --keepdb --noinput --verbosity=1` - 6 tests passed.
- Backend: `./venv/bin/python manage.py check` - no issues.
- Frontend: `npm run test:ci -- --include src/app/model/gst-compliance.spec.ts --include src/app/app-routing.module.spec.ts --include src/app/component/report/gstr1-gstr3b-reconciliation/gstr1-gstr3b-reconciliation.component.spec.ts --include src/app/component/report/gstr9report/gstr9report.component.spec.ts` - 41 tests passed.
- Frontend: `npm run typecheck` - passed.
- Browser: `npx playwright test playwright/tests/gst-report.spec.ts -g "Phase A"` - 1 test passed.
- Browser: `npx playwright test playwright/tests/gst-family-parity.spec.ts -g "Phase A"` - 1 test passed.
- Extended browser sweep: `npx playwright test playwright/tests/gst-report.spec.ts playwright/tests/gst-family-parity.spec.ts` - 30 tests passed, covering GST report, GSTR-3B, GSTR-9, exception dashboard, GSTR-1 vs GSTR-3B reconciliation, exports, empty states, mobile shell checks, and Phase A route contracts.

### Phase B: GST Compliance Center Snapshot API

Purpose: provide one backend summary payload for the umbrella screen.

Build scope:

- Add a read-only aggregation endpoint returning readiness cards, warnings, actions, and deep links.
- Reuse existing GSTR-1, GSTR-3B, reconciliation, exception, GSTR-9, GST portal, and reconciliation services.
- Return setup warnings instead of hard failures wherever possible.

Backend work:

- New service: compliance snapshot builder.
- New API: GST compliance center summary/readiness.
- Include status cards for:
  - GSTR-1
  - GSTR-3B
  - GSTR-1 vs GSTR-3B reconciliation
  - ITC / 2B
  - E-invoice / e-way
  - Exceptions
  - GST portal
  - GSTR-9
  - GST-TDS / TCS
- Add permission-aware `actions` and `deep_links`.

Frontend work:

- None required beyond API contract mock until Phase C.

Certification gate:

- API works for configured and partially configured entities.
- Missing static mappings, missing GSTIN, or missing provider credentials are visible warnings.
- Entity/FY/subentity isolation is proven by backend tests.

Phase B implementation status on 17 Sep 2026:

- Backend snapshot service added in `reports.gst_compliance.services`.
- Read-only API added at `/api/reports/gst-compliance/snapshot/`.
- Snapshot returns 9 umbrella cards: GSTR-1, GSTR-3B, GSTR-9, ITC/2B, GST Exceptions, GST Portal, E-Invoice/E-Way, GST-TDS, and TCS.
- Cards include status, blocker/warning counts, setup warnings, signals, access metadata, and canonical deep links.
- GSTIN resolution uses explicit scope GSTIN first, then subentity primary GSTIN, then entity primary GSTIN.
- Portal profile, portal filing run, GSTR-9 freeze, and GSTR-9 filing states are surfaced without recalculating report totals.
- Missing GSTIN and missing financial year are surfaced as warnings/blockers instead of hard crashes.

Phase B QA evidence:

- Backend: `./venv/bin/python manage.py test reports.tests_gst_compliance_contracts reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 10 tests passed.
- Backend: `./venv/bin/python manage.py check` - no issues.

### Phase C: GST Compliance Center UI Shell

Purpose: give accountants one user-friendly starting screen.

Build scope:

- One cockpit page using current app UI patterns.
- Top scope bar with entity, GSTIN, FY, period, subentity.
- Readiness cards for the GST work areas.
- Work queue sorted by blocked, needs review, ready.
- Deep links into existing pages with scope carried forward.
- No detailed report tables copied into this screen.

Frontend work:

- New component/page for GST Compliance Center.
- Service for snapshot API.
- Skeleton/loading/error/empty states.
- Route and menu integration.
- Responsive desktop/tablet/mobile layout.

Backend work:

- Small contract adjustments only if UI needs clearer labels/actions.

Certification gate:

- User can identify next GST action in under one minute.
- Every card opens the correct existing page.
- RBAC restricted users see access-safe states.
- Playwright covers route load, scope apply, card navigation, and mobile smoke.

Phase C implementation status on 17 Sep 2026:

- Frontend GST Compliance Center shell added at `/reports/compliance/gst-compliance-center`.
- Compliance Hub now exposes the GST Compliance Center as the primary GST entry point.
- Frontend snapshot service added for `/api/reports/gst-compliance/snapshot/`.
- Shared GST compliance model now includes snapshot payload, cards, setup warnings, next actions, links, and the umbrella route contract.
- Center UI includes compact scope controls, readiness summary, setup warnings, next-action queue, status cards, and deep links to canonical GST workspaces.
- The first certified drilldown opens GSTR-1 with the selected GST scope carried forward.
- Existing GST report, reconciliation, exception, GSTR-3B, and GSTR-9 screens remain canonical for detailed work.

Phase C QA evidence:

- Frontend focused specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/model/gst-compliance.spec.ts' --include='src/app/service/gst-compliance/gst-compliance-center.service.spec.ts' --include='src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts' --include='src/app/app-routing.module.spec.ts'` - 11 tests passed.
- Browser certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including GST Compliance Center route load, readiness cards, setup warnings, next-action queue, and GSTR-1 drilldown.

### Phase D: Output Tax And Filing Evidence Pack

Purpose: make outward GST numbers filing-defensible.

Build scope:

- Harden GSTR-1 vs GSTR-3B evidence.
- Include output GST ledger reconciliation.
- Add/export one filing evidence pack for outward tax review.

Backend work:

- Extend export pack to include GSTR-1 summary, GSTR-3B summary, reconciliation rows, output ledger tie-out, warnings, and generated metadata.
- Add golden scenario tests for B2B, B2C, export, SEZ, exempt/nil, non-GST, reverse charge, debit note, credit note, and amendments.

Frontend work:

- Add evidence pack action to reconciliation and/or cockpit.
- Keep drilldowns into current report pages and ledger book.

Certification gate:

- Every GSTR-1/3B variance has a clear reason or source drilldown.
- Exported evidence is usable by accountant/CA without manual stitching.

Phase D implementation status on 17 Sep 2026:

- GSTR-1 vs GSTR-3B reconciliation payload now includes a filing evidence pack.
- Evidence pack includes status, generated timestamp, normalized scope, reconciliation summary, output GST ledger summary, checklist, included section manifest, warnings, reconciliation rows, and output-tax ledger tie-out rows.
- Export endpoint now supports `evidence_json` for API automation and `evidence_csv` for accountant/CA filing evidence.
- Summary API exposes permission-aware evidence-pack export action.
- Frontend reconciliation page has an `Evidence Pack` action alongside existing Excel/CSV exports.
- Existing comparison grid, output GST ledger tab, advisories, source document drilldowns, and ledger drilldowns remain the working screens.

Phase D QA evidence:

- Backend: `./venv/bin/python manage.py test reports.tests_gst_reconciliation reports.tests_gst_compliance_contracts reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 19 tests passed.
- Backend: `./venv/bin/python manage.py check` - no issues.
- Frontend focused spec: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/report/gstr1-gstr3b-reconciliation/gstr1-gstr3b-reconciliation.component.spec.ts'` - 25 tests passed.
- Frontend: `npm run typecheck` - passed.
- Browser certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including the GSTR-1 vs GSTR-3B filing evidence pack download.

### Phase E: ITC / GSTR-2B / IMS Workspace Hardening

Purpose: make inward GST and ITC defensible.

Build scope:

- Connect GSTR-2B import/matching, purchase statutory review, and GSTR-3B ITC impact into one guided workflow.
- Add input GST ledger tie-out.
- Add decision evidence for accept/defer/reject/blocked ITC.

Backend work:

- Add input CGST/SGST/IGST/CESS ledger reconciliation against ITC classification.
- Strengthen matching outcomes: exact, partial, duplicate, missing in books, missing in portal, amended, credit note.
- Expose decision summary to cockpit.

Frontend work:

- Improve accountant path from cockpit to reconciliation run detail.
- Make decision states, bulk actions, and blocked reasons obvious.
- Ensure manual match and item drawer show source purchase invoice and ledger impact.

Certification gate:

- User can justify ITC claimed, deferred, rejected, and blocked.
- Playwright covers import/mock data, run review, manual match, bulk decision, and summary refresh.

Phase E implementation status on 17 Sep 2026:

- First ITC hardening slice completed: GST Compliance Center now prepares an input GST ledger tie-out against GSTR-3B net ITC.
- Backend compares Input CGST, Input SGST, Input IGST, and Input CESS static ledger mappings against GSTR-3B section 4 net ITC for the selected entity, financial year, subentity, and period.
- The tie-out payload includes component rows, configured/missing mapping status, return ITC, ledger ITC, variance, and ledger-book drilldown metadata.
- The ITC / 2B card now receives warning signals for input ledger mismatch count, total ITC variance, and ledger setup warning count.
- GST Compliance Center UI now shows a compact `Input GST ledger tie-out` evidence panel with GSTR-3B net ITC, input ledger balance, total difference, and component-level rows.
- Second ITC hardening slice completed: GST reconciliation items now expose structured ITC decision evidence for accept, defer, reject, and block decisions.
- ITC decision evidence is captured without a schema migration by storing a structured `itc_decision` object in reconciliation item metadata and writing an item audit log with decision details.
- Backend now supports a single-item `itc-decision` API plus a dedicated bulk ITC decision endpoint for reviewer queues.
- Frontend reviewer toolbar now includes Accept ITC, Defer ITC, Reject ITC, and Block ITC actions with required reason and optional claim period.
- Reconciliation item drawer now shows an `ITC Decision Evidence` panel so auditors can see decision, reason, claim period, decision timestamp, and match status at decision.
- Third ITC hardening slice completed: GST Compliance Center now rolls up the latest GSTR-2B purchase reconciliation run for the selected GSTIN/period.
- The ITC / 2B card now surfaces accepted, deferred, rejected, blocked, pending, decided item counts, and tax totals by decision bucket.
- Pending, deferred, rejected, or blocked ITC decisions now become visible cockpit warnings, so the accountant does not need to open every reconciliation item to know the period is still under review.
- GST Compliance Center now includes a compact `GSTR-2B decision summary` panel near the input GST ledger tie-out, showing review run status, decision counts, and accepted/deferred/blocked/pending ITC value buckets.
- Fourth ITC hardening slice completed: GSTR-2B purchase matching now creates idempotent `Missing In Return` review rows for eligible purchase invoices present in books but absent from imported 2B/portal rows.
- Missing-in-return rows preserve the purchase source document link, books-side tax values, structured mismatch reason, and document type, including purchase credit-note classification.
- The missing-in-return scan follows the existing purchase source eligibility rules: entity/FY/subentity scope, registered GST vendors, non-cancelled documents, and no import/composition vendor noise.
- Fifth ITC hardening slice completed: the GST reconciliation item detail API now exposes manual-match source document evidence and ledger impact for the linked books document.
- The item drawer now shows a compact `Source Document Evidence` panel with purchase invoice metadata and a `Ledger Impact` panel with debit/credit totals and posting journal lines, so reviewers can verify the books side without leaving the reconciliation workspace.
- Ledger impact lookup is additive and scoped by entity, FY, branch, source document type, and source document id. Existing reconciliation item/detail consumers remain compatible.
- Sixth ITC hardening slice completed: GSTR-2B purchase matching now detects amended rows, vendor-revised rows, and IMS actions from imported portal row metadata.
- Exact matches from amended/vendor-revised rows are routed to review instead of silent auto-match, preserving structured `PORTAL_ROW_AMENDED` and `PORTAL_ROW_VENDOR_REVISED` reasons.
- IMS accepted rows can auto-match but keep an informational `IMS_ACTION_ACCEPTED` reason; IMS pending/rejected rows are routed to review with `IMS_ACTION_PENDING` or `IMS_ACTION_REJECTED` evidence.
- Reconciliation run summaries now include `portal_context_summary` counts for amended, vendor-revised, IMS, IMS pending, and IMS rejected rows.
- GST Compliance Center now rolls these portal-context counts into the ITC / 2B card signals, warning stack, and the `GSTR-2B decision summary` panel, so reviewers can see IMS/amendment risk before opening the full run.

Phase E QA evidence:

- Backend: `./venv/bin/python manage.py test reports.tests_gst_compliance_snapshot reports.tests_gst_compliance_contracts --keepdb --noinput --verbosity=1` - 11 tests passed.
- Backend regression: `./venv/bin/python manage.py test reports.tests_gst_reconciliation reports.tests_gst_compliance_snapshot reports.tests_gst_compliance_contracts --keepdb --noinput --verbosity=1` - 20 tests passed.
- Backend ITC decision workflow: `./venv/bin/python manage.py test gst_reconciliation.tests --keepdb --noinput --verbosity=1` - 34 tests passed.
- Backend ITC decision cockpit roll-up: `./venv/bin/python manage.py test reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 6 tests passed.
- Backend contract/snapshot regression: `./venv/bin/python manage.py test reports.tests_gst_compliance_contracts reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 12 tests passed.
- Backend GSTR-2B missing-in-return matching: `./venv/bin/python manage.py test gst_reconciliation.tests --keepdb --noinput --verbosity=1` - 36 tests passed.
- Backend GST reconciliation/cockpit regression: `./venv/bin/python manage.py test gst_reconciliation.tests reports.tests_gst_reconciliation reports.tests_gst_compliance_snapshot reports.tests_gst_compliance_contracts --keepdb --noinput --verbosity=1` - 57 tests passed.
- Backend manual-match source and ledger evidence: `./venv/bin/python manage.py test gst_reconciliation.tests --keepdb --noinput --verbosity=1` - 37 tests passed.
- Backend GST reconciliation/cockpit regression after evidence drawer: `./venv/bin/python manage.py test gst_reconciliation.tests reports.tests_gst_reconciliation reports.tests_gst_compliance_snapshot reports.tests_gst_compliance_contracts --keepdb --noinput --verbosity=1` - 58 tests passed.
- Backend GSTR-2B portal-context/IMS hardening: `./venv/bin/python manage.py test gst_reconciliation.tests --keepdb --noinput --verbosity=1` - 39 tests passed.
- Backend GST reconciliation/cockpit regression after IMS hardening: `./venv/bin/python manage.py test gst_reconciliation.tests reports.tests_gst_compliance_snapshot reports.tests_gst_compliance_contracts reports.tests_gst_reconciliation --keepdb --noinput --verbosity=1` - 60 tests passed.
- Backend: `./venv/bin/python manage.py check` - no issues.
- Frontend focused specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts' --include='src/app/model/gst-compliance.spec.ts'` - 7 tests passed.
- Frontend ITC cockpit summary specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts' --include='src/app/model/gst-compliance.spec.ts'` - 8 tests passed.
- Frontend ITC decision focused specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/statutory/gst-reconciliation/gst-reconciliation-bulk-action-toolbar.component.spec.ts' --include='src/app/component/statutory/gst-reconciliation/gst-reconciliation-item-detail-drawer.component.spec.ts' --include='src/app/component/statutory/gst-reconciliation/gst-reconciliation-run-detail.component.spec.ts'` - 48 tests passed.
- Frontend source/ledger evidence drawer specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/statutory/gst-reconciliation/gst-reconciliation-item-detail-drawer.component.spec.ts' --include='src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts' --include='src/app/model/gst-compliance.spec.ts'` - 12 tests passed.
- Frontend IMS/amendment cockpit specs: `npx ng test --watch=false --browsers=ChromeHeadless --include='src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts' --include='src/app/model/gst-compliance.spec.ts'` - 8 tests passed.
- Frontend: `npm run typecheck` - passed.
- Browser certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including GST Compliance Center ITC card signal, Input SGST mismatch evidence row, and reconciliation drawer ITC decision evidence.
- Browser ITC cockpit summary certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including the GST Compliance Center `GSTR-2B decision summary` panel and decision-value buckets.
- Browser manual-match evidence certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including reconciliation drawer source document evidence and ledger impact.
- Browser IMS/amendment cockpit certification: `npx playwright test playwright/tests/gst-family-parity.spec.ts --project=chromium` - 8 tests passed, including Compliance Center amended-row, vendor-revised, and IMS-pending portal-context chips.
- Stage live browser certification after RBAC/menu and Phase E deployment: `PLAYWRIGHT_BASE_URL=https://accerio.in GST_BACKEND_URL=https://accerio.in TEST_USER_EMAIL='sushiljyotibansal@gmail.com' TEST_USER_PASSWORD='sushil' GST_LIVE_ENTITY_ID=3 GST_LIVE_ENTITY_FIN_ID=3 GST_LIVE_SUBENTITY_ID=3 npx playwright test playwright/tests/gst.live.spec.ts --project=chromium` - 9 tests passed, covering GSTR-1, GSTR-3B, GSTR-1 vs GSTR-3B, GST exception dashboard, GST Compliance Center navigation, GSTR-9, scope persistence, exports, and visual smoke.

Phase E remaining:

- Add reviewer-facing IMS action workflow once live provider payload/actions are finalized: accept/reject/pending action sync, provider status refresh, and stage certification against real WhiteBooks/portal IMS data.
- Stage-certify amended/vendor-revised/IMS datasets after deployment using a controlled imported return file or sandbox/provider payload.

### Phase F: E-Invoice And E-Way Period Monitoring

Purpose: move invoice-level compliance into period-level monitoring.

Build scope:

- Summarize IRN/EWB status by GSTIN and period.
- Surface failed, pending, cancelled, expired, retry-ready, and not-applicable counts.
- Deep link into sales invoice compliance workspace.

Backend work:

- Add aggregation over sales compliance states.
- Add provider readiness summary: credentials, sandbox/live mode, last error, retry blockers.

Frontend work:

- Cockpit card and drilldown for e-invoice/e-way health.
- Status labels aligned with sales invoice compliance workspace.

Certification gate:

- User can find all failed or pending e-invoice/e-way items from the GST cockpit.
- Existing sales invoice compliance workflow remains unchanged.

Phase F gap audit on 18 Sep 2026:

What is already implemented:

- Sales invoice compliance has mature invoice-level APIs and UI actions for IRN generation, combined IRN plus E-Way generation, B2B E-Way generation, B2C E-Way generation, IRN cancellation, E-Way cancellation, E-Way by IRN lookup, GSTIN sync, transporter lookup, HSN lookup, trip sheet, consolidated E-Way, multi-vehicle actions, vehicle update, transporter update, and validity extension.
- Sales compliance artifact models persist IRN/EWB status, numbers, acknowledgement dates, valid-up-to dates, request/response JSON, provider provenance, credential GSTIN, last error code/message, attempt count, and success timestamps.
- Backend state guards exist for generated/cancelled/not-applicable flows, including blocking IRN cancellation while an active E-Way exists.
- Existing frontend unit tests and browser tests cover many invoice-level flows: B2B/B2C generation, partial success, retry, duplicate IRN, E-Way timeout recovery, stale guidance clearing, reload stability, RBAC, and action payloads.
- The GST Compliance Center already exposes an `E-Invoice / E-Way` card and deep-link target into the sales compliance surface.

Confirmed gaps before Phase F implementation:

| Gap | Current behavior | Required behavior |
| --- | --- | --- |
| Period-level aggregation | The GST Compliance Center card only shows generic GSTIN/scope signals and permission/deep-link status. | Aggregate sales invoices for the selected entity, FY, subentity, GSTIN, and period/date range. |
| IRN health | Generated, pending, failed, cancelled, not-applicable, duplicate/error, and retry-ready IRN counts are not summarized in the umbrella. | Show IRN counts and status severity in the cockpit card. |
| E-Way health | Generated, pending, failed, cancelled, expired, expiring soon, not-applicable, missing transport data, and retry-ready EWB counts are not summarized in the umbrella. | Show EWB counts and expiry/transport warnings in the cockpit card. |
| Provider readiness | Provider name/environment exists on artifacts, but the cockpit does not summarize credential readiness, last provider error, or live/sandbox mode. | Add provider readiness signals and warnings. |
| Drilldown list | The cockpit opens the general sales compliance route, not a filtered list of affected invoices for this GSTIN/period. | Add a period-filtered drilldown or deep link carrying compliance filters. |
| Umbrella/workspace reconciliation | The cockpit card does not prove its counts agree with the invoice workspace artifacts. | Browser tests must compare card counts against mocked/controlled invoice-level detail data. |
| Stale/race safety | GST scope race tests exist for the center generally, but not for E-Invoice/E-Way aggregation changes. | Rapid GSTIN/period switching must prove stale IRN/EWB counts do not remain visible. |
| Certification data states | Invoice browser specs cover many flows, but the umbrella card lacks exhaustive ready/warning/error/blocked/not-configured/filed-like state coverage for this area. | Add deterministic Playwright states for normal, zero, warning, error, blocked, not configured, API failure, and permission restricted. |

Phase F development plan:

1. Backend aggregation service: query `SalesInvoiceHeader` joined to `SalesEInvoice` and `SalesEWayBill` using GST compliance scope.
2. Status classifier: convert artifact states into cockpit signals: ready, needs review, blocked, not configured, expired, expiring soon, retry-ready, and not applicable.
3. Snapshot integration: enrich the `einvoice_eway` card with IRN/EWB counts, warning/blocker messages, provider readiness, and a drilldown link.
4. Frontend presentation: render compact count chips on the card without disturbing the existing GST Compliance Center layout.
5. Browser certification: add Playwright tests that mock period datasets and validate summary counts, warnings, drilldowns, scope persistence, API payloads, permission restricted states, and stale-data/race behavior.

Phase F definition of done:

- The GST Compliance Center card can answer: how many invoices in this GSTIN/period are IRN-ready, IRN-generated, IRN-failed, EWB-generated, EWB-failed, cancelled, expired, expiring, retry-ready, and not applicable.
- Every warning on the card can be drilled back to the affected sales invoice/compliance workspace.
- Backend tests prove entity/FY/subentity/GSTIN/period scoping and cross-entity isolation.
- Playwright tests prove the cockpit card and workspace drilldowns remain aligned after scope changes, refresh, browser back/forward, and API failure.

Phase F implementation status on 18 Sep 2026:

- Backend aggregation added to the GST Compliance Center snapshot for the `E-Invoice / E-Way` card.
- The card now summarizes scoped sales invoices by entity, financial year, subentity, GSTIN, and return period/date range.
- Signals now include IRN generated/pending/cancelled, EWB generated/pending/cancelled, retry-ready count, not-applicable count, EWB expiring soon, missing transport detail, provider names, provider environments, and last provider error.
- Summary values now expose invoice count, IRN failed count, EWB failed count, and expired EWB count.
- Warnings/blockers are raised for failed items, pending items, expired EWB, expiring EWB, and incomplete transport detail.
- Existing invoice-level sales compliance workflow remains unchanged.

Phase F QA evidence:

- Backend focused tests: `./venv/bin/python manage.py test reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 8 tests passed.
- Frontend typecheck: `npm run typecheck` - passed.
- Browser focused certification: `npx playwright test playwright/tests/gst-einvoice-eway-cockpit.spec.ts --project=chromium --reporter=line` - 1 test passed, covering the E-Invoice/E-Way cockpit card counts, warnings/blockers, next action, sales compliance drilldown, scope query preservation, and browser back return.

### Phase G: Filing Lifecycle, Freeze, Amendments, And Portal Status

Purpose: control the return period from preparation to filing and amendment.

Build scope:

- Unified GST period lifecycle.
- Freeze/unfreeze or review lock where applicable.
- Portal prepare/save/status and evidence visibility.
- Amendment queue for previous-period changes.

Backend work:

- Period lifecycle model/service if not already sufficient.
- Link portal status and GSTR-9 freeze/status patterns into common lifecycle.
- Amendment impact summary.

Frontend work:

- Filing status strip in cockpit.
- Period checklist and amendment queue.
- Clear controls for freeze/reopen/file-ready actions, permission-gated.

Certification gate:

- A filed/frozen period cannot change silently.
- Amendment entries are traceable to source document and affected return period.

Phase G implementation status on 18 Sep 2026:

- Added a read-only `period_lifecycle` object to the GST Compliance Center snapshot.
- The lifecycle now resolves status from existing GST evidence instead of creating a parallel filing engine.
- Covered evidence sources:
  - GSTR-1 portal filing run.
  - GSTR-3B portal filing run.
  - GSTR-9 freeze snapshot.
  - GSTR-9 filing run.
- Lifecycle output includes status, label, GSTIN, period, portal return period, lock state, reopen eligibility, evidence rows, warnings, and blockers.
- Missing GSTIN now produces a lifecycle-level `not_configured` state with a blocker.
- Monthly periods become `filed` only when both GSTR-1 and GSTR-3B portal runs are filed for the selected GSTIN and return period.
- Prepared filing evidence takes precedence over an older freeze snapshot, matching existing GSTR-9 card behavior.
- Frontend cockpit now renders a compact filing lifecycle strip with status, GSTIN, return period, portal period, lock state, evidence rows, and blocker/warning messages.
- Added a read-only `amendment_queue` to the snapshot for prior-period impact review.
- Amendment queue sources now include current-period sales credit/debit notes linked to earlier-period invoices and GSTR-2B amended/vendor-revised portal context.
- Frontend cockpit now renders amendment item count, sales note count, portal revised count, tax impact, net impact, and top review rows.
- No existing filing, freeze, portal, GSTR-1, GSTR-3B, or GSTR-9 mutation workflow was changed.

Phase G QA evidence:

- Backend focused tests: `./venv/bin/python manage.py test reports.tests_gst_compliance_snapshot --keepdb --noinput --verbosity=1` - 11 tests passed.
- Django system check: `./venv/bin/python manage.py check` - passed.
- Frontend typecheck: `npm run typecheck` - passed.
- Angular focused unit tests: `npx ng test --watch=false --include src/app/component/report/gst-compliance-center/gst-compliance-center.component.spec.ts` - 14 tests passed.
- Browser focused certification: `npx playwright test playwright/tests/gst-period-lifecycle-cockpit.spec.ts --project=chromium --reporter=line` - 2 tests passed, covering filed lifecycle evidence, lock state, stable period metadata, not-configured state, no stale evidence, amendment queue rendering, no-impact hidden state, and no raw object rendering.
- Covered states: missing GSTIN/not configured, prepared annual lifecycle with freeze evidence, monthly filed lifecycle when both GSTR-1 and GSTR-3B are filed, linked sales note amendment impact, and GSTR-2B amended/vendor-revised portal context.

### Phase H: Calendar, Notices, Task Ownership

Purpose: turn GST from reporting into an operational compliance workspace.

Build scope:

- Compliance calendar by GSTIN and return type.
- Notice/task register with owner, due date, attachments, comments, and closure.
- Alerts from exceptions, filing deadlines, portal rejection, e-way expiry, and ITC risk.

Backend work:

- Calendar rules/service.
- Task/notice model or integration with existing task framework if available.
- Audit trail for task status changes.

Frontend work:

- Calendar/list view.
- Task drawer with owner/status/due date/attachments.
- Cockpit alerts.

Certification gate:

- User can see what is due, who owns it, and whether it is blocked.

### Phase I: Full Certification And Launch Matrix

Purpose: certify the GST umbrella for pilot/public launch.

Build scope:

- Backend regression suite.
- Angular focused specs.
- Playwright browser flows.
- Stage read-only validation and controlled mutation flows.
- Final launch confidence matrix.

Certification coverage:

- GSTR-1 report and export.
- GSTR-3B report and export.
- GSTR-1 vs GSTR-3B reconciliation.
- Output GST ledger tie-out.
- Input GST ledger tie-out.
- GSTR-2B import/match/decision.
- GST exception dashboard.
- Sales e-invoice/e-way period health.
- GST portal profile/status/evidence.
- GSTR-9 annual return readiness.
- GST-TDS/TCS deep links.
- RBAC access denied and permitted roles.
- Entity/FY/subentity/GSTIN isolation.
- Mobile/tablet visual smoke.

Launch gate:

- Final GST launch matrix is updated with evidence, residual risks, and confidence score.

## Launch Definition

Advanced GST Compliance is launch-ready when an accountant can:

- Configure entity GST registrations and compliance profile.
- Review GSTR-1 section-wise outward supply data and export/prepare filing payloads.
- Review GSTR-3B summary and reconcile it against GSTR-1, sales, purchase ITC, and ledger tax balances.
- Import/download GSTR-2B/IMS-style data, match it against purchase invoices, and track ITC decisions.
- Resolve GST exceptions with clear source document links and status history.
- Monitor e-invoice and e-way bill status, failures, cancellations, and retry readiness.
- Track return periods, due dates, filing status, amendments, and notices.
- Use one compliance cockpit to see what is ready, blocked, filed, amended, or risky.
- Pass RBAC, entity/FY/branch isolation, audit trail, browser, and stage certification.

## Phase Plan

### Phase 0: Inventory, Truth Map, And Gap Baseline

Status: baseline certified on 17 Sep 2026.

Purpose: document existing surfaces and identify launch blockers before implementation.

Tasks:

- Map backend routes, services, models, permissions, migrations, and tests for GST.
- Map frontend routes/components/services for GST.
- Identify duplicate/overlapping screens and decide canonical entry points.
- Build a compliance truth matrix:
  - GSTR-1 total vs sales register vs posted output-tax ledger.
  - GSTR-3B outward tax vs GSTR-1.
  - ITC available vs GSTR-2B/IMS vs purchase register vs input-tax ledger.
  - E-invoice/e-way status vs sales invoice state.
  - GST-TDS/TCS values vs statutory registers and ledgers.
- Establish baseline tests that already pass.

Baseline evidence captured on 17 Sep 2026:

- `reports.gstr1.tests.test_gstr1_report`, `reports.gstr3b.tests.test_gstr3b_summary`, and `reports.tests_gst_portal`: 124 tests passed.
- `gst_reconciliation.tests`, `reports.tests_gst_reconciliation`, and `reports.tests_gst_exception_dashboard`: 44 tests passed.
- GST portal WhiteBooks preview export was confirmed to work without live WhiteBooks credentials when the user has the correct export permissions.
- Corrected the GST portal preview export test fixture to include the current export permission codes: `reports.gst.export` and `reports.gstr3b.export`.

Launch gate:

- A single source-of-truth map exists before changing behavior. Baseline tests are green.

### Phase 1: Unified GST Compliance Cockpit

Purpose: give users one starting point for all GST work.

Functional scope:

- Period selector, GSTIN selector, entity/FY/subentity scope, and return-period status.
- Readiness cards for GSTR-1, GSTR-3B, 2B/ITC, e-invoice/e-way, exceptions, TDS/TCS, and filing tasks.
- Deep links into existing reports and workspaces.
- Clear status language: Ready, Needs Review, Blocked, Filed, Amendment Needed, Overdue.

Testing:

- Component/service tests for readiness aggregation.
- Browser tests for navigation to each GST surface.
- RBAC tests for restricted users.

Launch gate:

- A user can start GST work from one screen and understand the next action in under one minute.

### Phase 2: GSTR-1 And GSTR-3B Reconciliation Hardening

Status: in progress on 17 Sep 2026.

Purpose: certify outward supply and tax payable numbers.

Functional scope:

- Reconcile GSTR-1 sections with sales register.
- Reconcile GSTR-3B outward tax with GSTR-1 and output GST ledgers.
- Identify exempt/nil/non-GST, reverse charge, export, credit/debit note, and amendment mismatches.
- Trace each mismatch to source invoice/note/posting.
- Export evidence pack.

Progress on 17 Sep 2026:

- Added output GST ledger reconciliation to the GSTR-1 vs GSTR-3B payload.
- Output CGST, SGST, IGST, and CESS now compare GSTR-3B outward tax against posted output-tax ledger net credit using static account mappings.
- Missing output-tax ledger mappings are reported as setup warnings instead of causing report failure.
- Ledger rows include ledger-book drilldown metadata when the mapping exists.
- Added backend certification test proving CGST/SGST ledger matches and IGST/CESS missing mappings are visible.
- Added frontend Output GST Ledger tab on the GSTR-1 vs GSTR-3B reconciliation page.
- Frontend now shows return tax, ledger tax, difference, mapped ledger, missing static-account mapping state, and ledger-book drilldown.

Evidence on 17 Sep 2026:

- `reports.tests_gst_reconciliation`: 8 tests passed.
- `gst_reconciliation.tests`, `reports.tests_gst_reconciliation`, and `reports.tests_gst_exception_dashboard`: 45 tests passed.
- `reports.gstr1.tests.test_gstr1_report`, `reports.gstr3b.tests.test_gstr3b_summary`, and `reports.tests_gst_portal`: 124 tests passed.
- Angular focused spec `gstr1-gstr3b-reconciliation.component.spec.ts`: 23 tests passed.
- Frontend `npm run typecheck`: passed.
- Playwright mocked browser test `gst-family-parity.spec.ts -g "GSTR-1 vs GSTR-3B reconciliation"`: passed.

Testing:

- Backend golden dataset tests for B2B, B2C, CDN, export, exempt/nil, reverse charge, and amendments.
- Browser tests for smart filters, drilldowns, export, and source navigation.
- Stage read-only certification against current customer data.

Launch gate:

- GSTR-1 and 3B totals explain every variance with source links.

### Phase 3: GSTR-2B / IMS / ITC Workflow

Purpose: make purchase ITC defensible.

Functional scope:

- Import or ingest 2B/IMS-style supplier data.
- Match purchase invoices by GSTIN, invoice number, date, taxable value, tax amount, and filing period.
- Classify matched, partial match, missing in books, missing in portal, ineligible ITC, blocked credit, and deferred ITC.
- Bulk accept/defer/reject with audit trail.
- Feed ITC values into GSTR-3B summary and exception dashboard.

Testing:

- Import parser tests for 2B files and malformed rows.
- Matching tests for exact, fuzzy, duplicate, partial, amended, and credit note cases.
- Browser tests for bulk action, manual match, detail drawer, and supplier analytics.

Launch gate:

- A user can justify ITC claimed vs deferred vs blocked.

### Phase 4: E-Invoice And E-Way Bill Lifecycle Monitoring

Purpose: make sales compliance operationally safe.

Functional scope:

- Monitor IRN, acknowledgement, QR/artifact status, cancellation status, and provider error details.
- Monitor e-way generation, cancellation, expiry, transporter fields, distance/vehicle mode, and retry readiness.
- Connect invoice screen, compliance workspace, GST dashboard, and exception dashboard.
- Provider health/status and credential readiness checks.

Testing:

- Contract tests for action flags and state transitions.
- Browser tests for compliance actions, blocked states, retry states, and source invoice navigation.
- Stage sandbox smoke where credentials permit.

Launch gate:

- Every invoice shows whether e-invoice/e-way is not applicable, ready, generated, failed, cancelled, or needs correction.

### Phase 5: Filing Workflow, Amendments, And Return Status

Purpose: move from report viewing to controlled filing readiness.

Functional scope:

- Filing period lifecycle: open, prepared, reviewed, frozen, filed, amended.
- GST portal payload status and proceeded/accepted/rejected status.
- Amendment workflow for previous period invoices/notes.
- Freeze/unfreeze controls with audit.
- Filing checklist and evidence export.

Testing:

- API tests for period lifecycle.
- Amendment tests across original and amended period.
- Browser tests for freeze, review, filing status, and export.

Launch gate:

- A filed period cannot accidentally change without explicit amendment workflow.

### Phase 6: Notices, Calendar, And Operational Controls

Purpose: keep compliance work visible and timely.

Functional scope:

- GST compliance calendar by GSTIN and return type.
- Due date warnings and overdue status.
- Notice/task register with assignment, due date, attachments, remarks, and closure.
- Alert feed for failed e-invoice/e-way, return mismatch, ITC risk, and portal rejection.

Testing:

- Calendar date tests and overdue rules.
- Browser tests for notice/task creation, assignment, filtering, and closure.
- Mobile/tablet smoke for cockpit and task views.

Launch gate:

- Compliance risks are actionable before due date, not discovered after filing.

### Phase 7: RBAC, Audit, Stage Certification, And Launch Matrix

Purpose: certify the vertical for pilot/public launch.

Functional scope:

- Permissions by action: view, prepare, import, match, approve, freeze, export, file, amend, notice manage.
- Entity/GSTIN/FY/branch isolation.
- Audit logs for import, match, override, freeze, export, file, amend, and notice closure.
- Cross-browser and mobile/tablet checks.
- Performance checks for large 2B/GSTR-1 datasets.

Testing:

- Backend permission/scope tests.
- Angular route/service tests.
- Playwright mocked workflow tests.
- Stage live read-only and controlled mutation tests.

Launch gate:

- Final GST launch matrix has evidence for every critical workflow.

## Initial Priority Recommendation

Start with Phase 0 and Phase 2 together:

- Phase 0 gives the map and prevents duplicate work.
- Phase 2 is the highest accounting-risk area because GSTR-1/3B numbers must reconcile to books before customers trust the product.

Then proceed to Phase 3 because ITC/2B mismatches are the next highest customer pain point.

## Initial Confidence

- Sales compliance/e-invoice/e-way foundation: high.
- GST reconciliation/2B foundation: medium-high.
- GSTR-1/3B reporting foundation: medium-high.
- Unified cockpit and filing lifecycle: medium.
- Full Advanced GST Compliance launch confidence today: 78%.

Confidence should move above 90% after:

- Phase 0 truth map is complete.
- GSTR-1/3B reconciliation has golden dataset and stage evidence.
- 2B/ITC workflow has stage browser certification.
- Filing/freeze/amendment workflow is certified.

## Open Decisions

- Whether filing submission is in-scope for launch or whether launch stops at filing-ready payload/evidence.
- Whether IMS is implemented as a distinct workflow or absorbed into the 2B/ITC workspace first.
- Whether GST notice management is P1 launch scope or pilot/P2.
- Whether provider integrations should stay WhiteBooks-only for launch or support additional providers later.
