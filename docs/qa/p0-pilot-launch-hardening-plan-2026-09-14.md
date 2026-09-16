# P0 Pilot And Launch Hardening Plan

Status: In progress

Last updated: 15 September 2026

Parent roadmap: [Product Expansion Priority Roadmap](../product/product-expansion-priority-roadmap-2026-09-14.md)

Paired launch gate: [P1 HRMS And Payroll Launch Readiness Plan](../payroll/p1-hrms-payroll-launch-readiness-plan-2026-09-14.md)

## 1. Objective

Certify the currently supported Finacc ERP scope for a controlled pilot and then public launch. P0 is complete only when business correctness, accounting integrity, tenant isolation, recovery, usability, performance, deployment, and support readiness have objective evidence.

P0 does not add large new product verticals. Functional gaps discovered during certification are either fixed when required for the supported scope or recorded as explicit non-goals with owner approval.

## 2. Portfolio Gate

`P2` and later product-expansion implementation must not begin until both conditions are true:

1. P0 has a signed `Pilot Ready` or `Public Launch Ready` decision for the core ERP scope.
2. P1 has a signed `Launch Ready` decision for the supported HRMS/payroll scope.

Discovery may continue, but production implementation for later workstreams remains frozen until this combined gate is met.

## 3. Supported Launch Scope

P0 certifies the implemented portions of:

- Identity, signup, entity onboarding, financial years, branches, subentities, and platform operations.
- RBAC, subscriptions/entitlements, object actions, entity/branch/FY isolation, and audit history.
- Financial masters, vouchers, posting, reversal, allocations, daybook, ledgers, trial balance, P&L, balance sheet, trading account, and close controls.
- Sales, receivables, receipts, GST/TCS/TDS effects, notes, imports, printing, and exports.
- Purchase, payables, payments, GST/ITC/RCM/TDS effects, notes, imports, and exports.
- Inventory, stock movement, valuation, batch/location control, manufacturing, production costing, and accounting reconciliation for declared supported workflows.
- Assets and depreciation for declared supported workflows.
- GST, TDS, TCS, e-invoice/e-way bill, reconciliation, and compliance reports for configured integrations.
- Capital distribution and organization-form behavior already marked supported.
- HRMS/payroll foundations only where P1 separately marks them launch ready.

## 4. Certification Rules

- A passing API is not proof of a working screen.
- A passing screen is not proof of accounting correctness.
- A balanced journal is not proof of correct account classification.
- A local pass is not staging certification.
- A single clean run is not repeatability evidence.
- A superuser pass is not RBAC certification.
- A desktop Chromium pass is not browser, mobile, or accessibility certification.
- Known unsupported behavior must be visible in-product or prevented, not silently left to operator knowledge.

## 5. Phase Plan

### Phase 0: Scope Freeze And Traceability

Status: In progress; inventory baseline complete, approvals pending

Working register: [P0 Core Launch Scope And Traceability Register](p0-core-launch-scope-traceability-register-2026-09-14.md)

Goal: establish exactly what is being launched and where every claim is proved.

Work:

- Build a route, screen, API, action, role, posting, report, and test inventory.
- Merge current module QA plans into one launch matrix without deleting detailed evidence.
- Mark every item `Supported`, `Conditional`, `Unsupported`, or `Backlog`.
- Map each supported business event to expected journal lines, subledger effect, inventory effect, tax effect, and report effect.
- Record production dependencies, external providers, scheduled jobs, secrets, storage, and infrastructure owners.
- Freeze launch scope and establish defect severity/waiver rules.

Exit evidence:

- No supported route, API, lifecycle action, or accounting event lacks an owner and test reference.
- Product, accounting, engineering, QA, and operations approve the scope register.

### Phase 1: Identity, Onboarding, Scope, And Access

Status: In progress; staging identity/session, restricted-role, branch-isolation, and HRMS persona gates passed; broader object and recovery isolation remains

Goal: prove that users enter the correct tenant and can access only the correct data and actions.

Work:

- Test signup, GST lookup/autofill, platform-led onboarding, customer-led onboarding, activation, login, logout, password reset, expiry, and session recovery.
- Test platform operator, entity admin, accountant, approver, operator, employee, read-only, and restricted roles.
- Test direct URLs, menus, APIs, exports, attachments, print, background jobs, and object actions under positive and negative permissions.
- Switch entity, branch, subentity, FY, and role while reports and transactional screens are open.
- Verify stale-context, missing-branch, inactive-FY, closed-period, and removed-membership behavior.
- Confirm all allowed menus are visible and all denied menus/actions are absent or explain access clearly.

Exit evidence:

- No cross-tenant, cross-entity, cross-branch, or cross-FY data exposure.
- No privileged operation can be invoked through a hidden direct route or API.
- Onboarding creates the same required masters and policies through public and platform-admin paths.

### Phase 2: Core Accounting And Close Integrity

Status: Complete for the pilot gate. Backend close invariants pass 37/37, the three-browser controls surface certificate passes 45/45, and the deployed isolated self-cleaning destructive staging certificate passes 2/2. The browser cycle proves close, duplicate rejection, closed-period posting rejection, UI opening carry-forward generation, source-FY retention, visible UI rollback, rollback ordering, opening purge, close rollback, restored readiness, and zero temporary user/entity residue. The focused frontend component suite passes 25/25.

Goal: certify the general ledger and financial statements as the common source of truth.

Work:

- Test account masters, classifications, opening balances, journals, cash/bank/contra vouchers, allocations, posting, unposting/reversal, and audit trails.
- Verify account usage filters prevent revenue, expense, party, asset, liability, tax, and bank misclassification.
- Reconcile source document to posting detail, daybook, ledger book, ledger summary, trial balance, P&L, trading account, balance sheet, cashbook, and relevant subledger.
- Test branch/all-branch scope, comparative periods, custom date ranges, opening/closing logic, retained earnings, capital distribution, year-end close, reopen, and locked periods.
- Test rounding, decimal precision, negative values, zero-value documents, backdating, future dates, and prior-period adjustments.

Exit evidence:

- Debit equals credit for every posting and reversal.
- Trial balance is balanced and statement equations reconcile under all supported scopes.
- No confirmed-only or reversed document is presented as actively posted.
- Three independent test datasets reproduce expected accounting results.

### Phase 3: Sales, Purchase, Receivables, Payables, And Banking Baseline

Status: In progress. The combined backend commercial baseline passes 1,062/1,062 tests. The selected live staging gate passes six business scenarios in Chromium: bank reconciliation and source integrity, purchase-to-payment, payables payment reconciliation, seeded receivables reconciliation, and the service-invoice-to-receipt super-flow. The complete goods/service sales and purchase note reconciliation selection passes all 16 business scenarios when run in bounded specification processes; the sales-note specification passes 7/7 including authentication in 3.7 minutes. All 12 document surfaces also pass GST symmetry and lookup-pagination coverage, 25/25 including authentication. The expanded settlement certificate passed 17/17 across three bounded Chromium runs, covering cash/bank, partial, advance-adjusted, multi-document, policy-off, over-settlement block/warn, FIFO/manual allocation, and the AP mirror. Purchase-payment concurrency, retry idempotency, and entity/FY/branch isolation passed 4/4. Taxability preservation passed 15/15 including setup across Chromium, Firefox, and WebKit. Purchase-register XLSX, CSV, PDF, and browser-print output passed 2/2 including content verification. Payables direct-export certification covers 16 AP/payables report surfaces, and receivables direct-export certification covers customer outstanding, credit exposure, overdue customers, exceptions, aging, open items, customer ledger, and collections history across Excel, CSV, PDF, and print endpoints on staging. The sales print selection passed 14/18 on the pre-fix staging build; the multi-page 35-line browser/PDF case now passes after fixture hardening, and the modal-ownership correction passes 348 component tests plus a production build. Remaining Phase 3 work is broader output coverage, accessibility certification, and the explicit infrastructure restore rehearsal.

Goal: certify daily commercial document and settlement cycles.

Work:

- Execute all supported goods/service invoices, credit/debit notes, returns, charges, discounts, taxability, RCM, cess, TDS/TCS, and registered/unregistered/non-GST permutations.
- Test draft, edit, confirm, approve, post, print/export, unpost/reverse, cancel, copy, previous/next, find, and pagination.
- Reconcile sales documents to revenue, GST, inventory/COGS, AR, receipts, allocations, aging, and customer ledgers.
- Reconcile purchase documents to expense/asset/inventory, GST/ITC/RCM, AP, payments, allocations, aging, and vendor ledgers.
- Test partial, advance, over, short, split, unallocated, refunded, written-off, and reversed settlements.
- Test account classification and fallback policies with deliberately invalid master data.

Exit evidence:

- Source, subledger, tax register, inventory, posting, settlement, and financial reports agree.
- No retry, double-click, timeout, or concurrent request creates duplicate documents, allocations, or postings.

### Phase 4: Inventory, Manufacturing, Assets, And Operational Reconciliation

Status: In progress. Inventory report reconciliation and concurrency gates are complete, and the direct export gate now covers Stock Summary, Stock Ledger, Stock Aging, Stock Movement, Location Stock, Stock Day Book, Stock Book Summary, Stock Book Detail, Non-Moving Stock, Slow Moving vs Dead Stock, and Reorder Status across usable Excel, CSV, PDF, and print payloads on staging. Manufacturing is certified for supported report/API correctness and production-costing flows, but manufacturing reports do not currently expose export endpoints.

Goal: close the open launch matrix in the existing operational-module plans.

Work:

- Complete inventory masters/opening position, quantity movement, valuation, batch/location, negative-stock, backdate, transfer, adjustment, count, and reversal testing.
- Complete supported manufacturing execution, consumption, output, scrap/by-product, WIP, costing, variance, reversal, and production-report testing.
- Test asset acquisition, capitalization, transfer, depreciation, impairment/revaluation where supported, disposal, reversal, and asset/GL reconciliation.
- Verify sales/purchase/manufacturing/assets share consistent stock and accounting results.
- Execute volume and concurrency scenarios for the supported operational scope.

Exit evidence:

- Quantity by location/batch/serial, valuation layers, stock reports, production records, asset registers, and GL agree.
- Existing module launch matrices contain no unexplained `Pending` item inside supported scope.

### Phase 5: Statutory Compliance And External Providers

Status: Not started

Goal: prove tax correctness and controlled provider behavior without exposing secrets or duplicating submissions.

Work:

- Reconcile GST, ITC, RCM, TDS, and TCS from source documents through registers, returns, liability/credit ledgers, payments, and GL.
- Test GSTR and reconciliation workflows, amendments, cancellations, notes, exports/SEZ, advances, exemptions, and nil/non-GST cases in supported scope.
- Test e-invoice/e-way bill authentication, generation, cancellation, status polling, expiry, throttling, provider outage, malformed response, timeout, and retry.
- Verify HSN/SAC and tax-policy effective dates, mandatory fields, percentages, paired CGST/SGST behavior, IGST behavior, cess, and rounding.
- Confirm provider credentials and payloads are redacted from UI, logs, traces, test artifacts, and error responses.

Exit evidence:

- No statutory summary differs from its supporting register or GL without an explained adjustment.
- Provider retries are idempotent and operational diagnostics identify actionable failure causes.

### Phase 6: Failure, Recovery, Concurrency, And Data Protection

Status: In progress; payroll recovery, deployed commercial lifecycle idempotency, rapid-action protection, cross-browser session recovery, and portable commercial transport recovery are certified

Goal: demonstrate that failures are recoverable and cannot silently corrupt accounting state.

Work:

- Inject 401, 403, 409, 422, 429, 500, timeout, disconnect, offline, interrupted upload/download, worker restart, and provider failure.
- Test optimistic concurrency, stale versions, double submit, repeated callbacks, concurrent posting, concurrent stock issue, and concurrent allocation.
- Verify atomic rollback for document/import/payment/manufacturing/payroll transactions.
- Test import duplicate detection, partial-failure policy, retry manifests, and large-file recovery.
- Rehearse database backup, object/file backup, point-in-time recovery where supported, restore verification, and disaster failover steps.
- Verify retention, deletion, attachment access, audit immutability, and sensitive-data masking.

Exit evidence:

- Recovery-point and recovery-time objectives are measured and accepted.
- No injected failure creates an unbalanced journal, orphan stock move, duplicate settlement, or ambiguous external submission.

### Phase 7: UX, Mobile, Accessibility, And Browser Certification

Status: In progress. Core financial statement CSV, print, keyboard, overflow, and automated WCAG A/AA certification passes 39/39 locally across Chromium, Firefox, and WebKit. A serious non-focusable scroll-region issue was corrected across P&L, Balance Sheet, and Trading Account; the focused Angular statement suite passes 82/82 and type checking is clean. Staging rerun, remaining critical screens, manual screen-reader review, and visual-baseline approval remain open.

Goal: certify every supported critical screen from an end-user perspective.

Work:

- Review every visible field, label, dropdown, table, dialog, action, pagination state, validation, message, loading, empty, error, and success state.
- Verify desktop, tablet, and mobile layouts, including navigation, compact header, sticky actions, tables, zoom, orientation, and virtual keyboard behavior.
- Run Chromium, Firefox, and WebKit critical workflows and visual baselines.
- Run automated accessibility scans and manually test keyboard-only use, focus order, focus visibility, names, labels, errors, dialogs, and screen-reader critical paths.
- Validate user language: no raw backend traceback, HTML error page, implementation detail, or misleading status.

Exit evidence:

- No critical workflow is blocked at a supported viewport or browser.
- No unresolved serious/critical accessibility violation.
- Product owner approves stable visual baselines and manual assistive-technology evidence.

### Phase 8: Performance, Scale, And Repeatability

Status: Not started

Goal: demonstrate predictable behavior under pilot and launch load.

Work:

- Define budgets for login, initial shell, list, search, save, post, report, export, PDF, import validation/commit, payroll, stock movement, and background jobs.
- Test representative and worst-supported tenant data volumes.
- Exercise concurrent users by role and transaction mix, not only isolated endpoint load.
- Test 100/500/1,000-document generation/import batches where supported.
- Detect slow queries, N+1 access, lock contention, queue backlog, memory growth, and cache inconsistency.
- Run the full launch suite three times against an unchanged staging build.

Exit evidence:

- Agreed percentile budgets pass with no accounting or isolation error.
- Three consecutive suites pass without flaky-test waiver or manual data repair.

### Phase 9: Deployment, Observability, Support, And Pilot Rehearsal

Status: Not started

Goal: prove that the release can be deployed, monitored, supported, and rolled back safely.

Work:

- Rehearse migrations, static/frontend deployment, workers/schedulers, health checks, cache behavior, and rollback on a production-like copy.
- Verify structured logs, correlation IDs, audit events, metrics, alerts, dashboards, and provider/job diagnostics.
- Remove or protect debug behavior, test credentials, generated screenshots, traces, videos, and temporary artifacts.
- Execute a scripted end-to-end pilot day using realistic users and opening data.
- Complete support runbooks, incident severity, escalation, customer communication, known limits, and rollback decision tree.
- Record go/no-go approvals and residual risks.

Exit evidence:

- Deployment and rollback rehearsal passes.
- Monitoring detects simulated critical failures.
- Pilot launch matrix is signed by product, accounting, engineering, QA, security/operations, and support owners.

## 6. Required Business Permutations

The traceability matrix must cover at least:

- GST registered, composition/exempt where supported, unregistered, and non-GST entities/parties.
- Goods, services, assets, expenses, inventory, and mixed documents.
- Intra-state, inter-state, export/SEZ where supported, RCM, cess, discounts, freight/charges, and withholding.
- Draft, confirmed, approved, posted, partially settled, fully settled, reversed, cancelled, and locked-period states.
- Head office, branch, all-branch, subentity, multiple FYs, and entity switching.
- Admin, accountant, maker, checker/approver, operator, read-only, employee, restricted, and platform roles.
- Empty, single-row, multi-row, high-volume, duplicate, stale, malformed, interrupted, and concurrent requests.

## 7. Defect And Waiver Policy

| Severity | Meaning | Launch rule |
| --- | --- | --- |
| S1 | Data loss, tenant leak, security compromise, unbalanced/incorrect core accounting, unrecoverable outage | No waiver; blocks pilot and public launch |
| S2 | Incorrect tax/subledger/report, duplicate commit, material workflow failure, inaccessible critical workflow | Blocks launch unless removed from supported scope with owner approval and technical prevention |
| S3 | Workaround exists without data/compliance risk | Requires owner, target release, documented workaround, and monitored pilot acceptance |
| S4 | Cosmetic or low-impact usability issue | May enter backlog with product approval |

## 8. P0 Launch Matrix

| Gate | Status | Evidence | Blocking defects | Owner approval |
| --- | --- | --- | --- | --- |
| Scope and traceability | In progress | [P0 scope register](p0-core-launch-scope-traceability-register-2026-09-14.md) | Scope/owner/dependency approvals pending | - |
| Identity, onboarding, RBAC, and isolation | In progress | Identity: Chromium 9/9 and Firefox/WebKit 12/12; restricted browser routes 27/27; deployed live menu/API/export/payroll/cross-entity denial passed in Chromium, Firefox, and WebKit; deployed branch isolation plus HRMS viewer and ESS approval boundaries passed in Chromium; valid-parent attachment denial passed for five financial document families; direct sensitive-payroll denial passed for real profile, salary-assignment, run, posting-status, calculation-action, and payment-batch objects; PostgreSQL regressions cover the wider sensitive-object matrix | Direct staging tax-declaration, published-payslip, and FnF probes await governed fixtures; failure/recovery/concurrency isolation remains | - |
| Core accounting and close | Complete for pilot gate | Backend close invariants 37/37; controls surface 45/45 across three browsers; isolated destructive close/opening cycle 2/2; frontend components 25/25 | No blocking defect in certified scope | - |
| Sales/AR and purchase/AP | In progress | Combined backend commercial baseline 1,062/1,062; selected staging bank, purchase/payment, payables, receivables, and sales/receipt scenarios pass in Chromium; all 16 goods/service invoice and note reconciliation scenarios pass in bounded runs; 12-surface GST symmetry and lookup pagination pass 25/25; expanded AR/AP settlement groups pass 17/17; payment concurrency/retry/isolation passes 4/4; taxability preservation passes 15/15 across three engines; purchase lifecycle idempotency passes 12/12 and rapid confirm/post/unpost/cancel protection passes 24/24; sales invoice rapid-action protection passes 8/8 and sales-note protection passes 16/16; voucher lifecycle idempotency passes 5/5; rejected-action and transport recovery are certified; purchase-register XLSX/CSV/PDF/print output passes content verification; the 35-line sales PDF browser case passes; sales print modal correction passes 348 component tests and a production build; payables direct-export certification covers 16 report surfaces and passed on staging in Chromium; receivables direct-export certification covers customer outstanding, credit exposure, overdue customers, exceptions, aging, open items, customer ledger, and collections history and passed on staging in Chromium; voucher PDF certification covers cash, bank, journal, payment, and receipt voucher families on staging | Complete remaining output families and accessibility certification | - |
| Inventory/manufacturing/assets | In progress | Inventory reconciliation 24/24 across three browsers; inventory concurrency 3/3; inventory direct-export certification covers 11 stock/control report surfaces and passed 4/4 focused staging checks in Chromium; manufacturing report/API correctness passed 24/24 on staging; asset purchase-to-capitalization/reversal lifecycle passed with exact ledger restoration; asset report export gate now covers fixed asset register, depreciation schedule, location/custodian, and events | Deploy the asset Excel sheet-title correction, rerun asset report output certification on staging, then complete accessibility/mobile certification | - |
| Statutory compliance/providers | Not started | Existing module evidence to consolidate | Not assessed | - |
| Failure, concurrency, and recovery | In progress | Payroll PostgreSQL lifecycle/concurrency/rollback regression passed 108/108; onboarding readiness server/network recovery passed 15/15 locally and the combined deployed staging gate passed 18/18 across three engines, with 48/48 focused Angular tests; deployed login-500 and GST-provider retry passed 9/9 across three engines; expired-session recovery passed 6/6 across three engines; purchase idempotency/rapid actions passed 36/36 business scenarios; sales invoice/note rapid actions passed 24/24; payment-voucher idempotency passed 5/5; rejected purchase actions preserved state in 4/4; sales 500/409 failure-then-retry passed 15/15 invoice/note scenarios; staging recovery passed for 401/403/409/422/429/500, timeout, disconnect, offline download, interrupted upload, exactly-once purchase import commit, lost commit response, and successful retry, with the new rejection matrix passing across Chromium, Firefox, and WebKit | Controlled staging transaction concurrency needs an isolated test-database role; worker restart, provider callback failure, backup/restore, and disaster recovery remain | - |
| UX, browsers, mobile, and accessibility | In progress | Core financial statements pass 39/39 locally across Chromium, Firefox, and WebKit for scoped CSV, authenticated print, keyboard export access, overflow, and automated WCAG A/AA scanning; focused Angular statements pass 82/82. The first no-override staging run exposed a transient 1.11:1 P&L Smart Filter contrast state during simultaneous foreground/background hover interpolation; the shared transition correction is locally verified. | Deploy the color-transition correction and rerun the complete statement certificate on staging; complete remaining critical screens, manual screen-reader review, and visual-baseline approval | - |
| Performance and repeatability | Not started | - | Not assessed | - |
| Deployment, monitoring, and support | Not started | - | Not assessed | - |
| Pilot decision | Pending | - | Not assessed | - |
| Public-launch decision | Pending | Requires pilot evidence | Not assessed | - |

## 9. Phase Update Log

| Date | Phase | Change | Evidence | Result | Next action |
| --- | --- | --- | --- | --- | --- |
| 16 September 2026 | Phase 4 | Added asset report direct-export certification and fixed the first blocker it exposed. | `assets.live.spec.ts` now validates fixed asset register, depreciation schedule, asset location/custodian, and asset events export URLs across Excel, CSV, PDF, and print. The first staging Chromium run found a real 500 on location/custodian Excel. Local regression `assets.tests.AssetApiScopeTests.test_report_location_custodian_excel_export_uses_valid_sheet_title --keepdb` passes after sanitizing asset Excel worksheet titles. | Backend fix is ready; staging remains red until deployment because the live endpoint still runs the old sheet-title code. | Deploy backend, rerun `assets.live.spec.ts -g "asset operational reports live exports"` on staging, then continue asset accessibility/mobile checks. |
| 16 September 2026 | Phase 4 | Added and ran the inventory direct-export certification gate on staging. | `inventory.live.spec.ts` now uses `PLAYWRIGHT_BACKEND_URL` and verifies Stock Summary, Stock Ledger, Stock Aging, Stock Movement, Location Stock, Stock Day Book, Stock Book Summary, Stock Book Detail, Non-Moving Stock, Slow Moving vs Dead Stock, and Reorder Status export URLs. Focused Chromium staging runs passed 4/4: the new location/book sweep passed 1/1 in 10.7 seconds, and the existing summary/control/aging export checks passed 3/3 in 29.2 seconds. | Inventory output coverage now has endpoint payload certification across Excel, CSV, PDF, and print for all implemented inventory report export surfaces. | Continue asset report output certification, then rerun operational accessibility and mobile checks. |
| 15 September 2026 | Phase 7 | Diagnosed the intermittent P&L contrast failure from the no-override staging certificate. | The full Chromium sequence reproduced a serious Axe finding on Smart Filter at 1.11:1; enriched node evidence showed both foreground and background caught mid-transition. Five focused P&L workflow repetitions passed, isolating the timing condition. Type checking and the 82-test statement component suite pass after the shared CSS correction. | Contrast-critical foreground and background colors now switch atomically while border, shadow, and movement transitions remain animated. This removes the transient inaccessible frame across shared buttons. | Deploy the frontend correction and rerun all 39 statement output/accessibility checks across Chromium, Firefox, and WebKit. |
| 16 September 2026 | Phase 3 | Added and ran payables-family direct export certification on staging. | `payables.live.spec.ts` now verifies 16 AP/payables report surfaces expose and serve Excel, CSV, PDF, and print outputs. The focused Chromium staging run passed 1/1 in 38.1 seconds. | Payables output coverage is no longer limited to AP aging, upcoming payments, and purchase register UI buttons; the broader family now has endpoint payload certification. | Extend the same output gate to the remaining non-payables families, then continue accessibility certification. |
| 16 September 2026 | Phase 3 | Added and ran voucher-family PDF certification on staging. | `vouchers.live.spec.ts` now discovers cash, bank, journal, payment, and receipt voucher rows and verifies each PDF endpoint returns non-empty `application/pdf` output with a PDF signature and filename. The focused Chromium staging run passed 1/1 in 7.4 seconds; live scope counts were cash 56, bank 33, journal 32, payment 266, receipt 27. | Voucher print/PDF coverage is now endpoint-certified instead of only covered by lifecycle and browser navigation checks. | Continue remaining non-payables output certification, then accessibility certification. |
| 16 September 2026 | Phase 3 | Hardened and ran receivables-family direct export certification on staging. | `receivables.live.spec.ts` now uses `PLAYWRIGHT_BACKEND_URL` for login/RBAC/export requests and parameterized live customer export URLs. The focused Chromium staging run passed 1/1 in 26.1 seconds across customer outstanding, credit exposure, overdue customers, receivables exceptions, aging summary/invoice, open items, customer ledger, and collections history. | AR output coverage now mirrors AP/payables with direct endpoint payload certification across Excel, CSV, PDF, and print. | Continue the remaining output families, then complete accessibility certification. |
| 15 September 2026 | Phase 7 | Added and ran the financial statement output/accessibility certificate. | Trial Balance, P&L, Balance Sheet, and Trading Account passed 39/39 across Chromium, Firefox, and WebKit; focused Angular statement tests passed 82/82 and type checking passed. | A serious Trading Account scroll region lacked keyboard access. The correction was applied consistently to the paired P&L, Balance Sheet, and Trading Account tables. The Playwright certificate now retains one browser session per engine and runs engines sequentially to avoid refresh-token invalidation. | Deploy the frontend and rerun without overrides on staging, then extend the same certificate to Daybook, Ledger Book/Summary, Cash/Bank Book, registers, and remaining document outputs. |
| 15 September 2026 | Phase 3 | Corrected the shared sales-document utility header. | The focused Angular suite passes 348/348 with one intentional skip; type checking and the production build pass. Six new `FIN-SALES-HEADER-*` browser cases cover all invoice/note routes at desktop, tablet, and mobile dimensions. | Compliance, Find, Transport Details, and Reset now share a compact aligned desktop rail, equal sizing, accessible names, and contained horizontal scrolling on smaller viewports. | Deploy the frontend and run the six-route header matrix without overrides across Chromium, Firefox, and WebKit. |
| 15 September 2026 | Phase 3 | Corrected and certified the sales print preview for tablet and mobile viewports. | The combined sale-invoice and shared tax-invoice component suite passes 362 tests, the post-diagnosis shared component check passes 14/14, and the Angular production build succeeds. After deployment, `FIN-SAL-PR-033` passed in Chromium, Firefox, and WebKit at 820x1180 tablet and 390x844 phone dimensions, including dialog containment, useful preview height, horizontal A4 panning, and accessible controls. | Inspection confirmed GST Validation was a third grid child while responsive CSS declared only two rows, causing a full-height implicit row and an 8px preview. The deployed grid now explicitly allocates toolbar, preview, and a bounded scrollable validation row. | Continue cross-browser output-content and accessibility certification for the remaining document print surfaces. |
| 15 September 2026 | Phase 3 | Started document print/export certification and corrected competing sales dialogs. | Purchase Register export passed 2/2 including XLSX, CSV, extracted PDF content, filename, filter scope, and browser print. The 35-line multi-page browser/PDF case passes in 1.3 minutes. After deployment, `FIN-SAL-PR-017`, `018`, and `031` passed 3/3 business checks plus setup in Chromium, covering profile switching, standard/thermal downloads, and popup geometry. | The late confirmation-summary response no longer reopens above the print dialog. The multi-line fixture is deterministic while retaining full browser output assertions. | Continue cross-browser output-content and accessibility certification for the remaining document print surfaces. |
| 15 September 2026 | Phase 6 | Completed the deployed commercial lifecycle idempotency and rapid-action recovery matrix. | Purchase: 12/12 repeated confirm/post and 24/24 rapid confirm/post/unpost/cancel business scenarios across six goods/service invoice/note types. Sales: 8/8 invoice and 16/16 note rapid-action scenarios. Payment voucher: 5/5 submit/approve/post/unpost/cancel idempotency scenarios. Browser setup checks also passed in each bounded run. | No duplicate write, duplicate document, unstable terminal state, or UI/API status mismatch was observed. Two Playwright-only defects were corrected: unbounded footer-action probes exhausted the stage test budget, and the confirm-race parity oracle expected Draft (`1`) instead of Confirmed (`2`). | Add endpoint-specific transport-failure injection for commercial saves/posts, then execute print/export and accessibility certification; keep SMTP and infrastructure restore rehearsal as explicit launch dependencies. |
| 15 September 2026 | Phase 6 | Executed deployed commercial endpoint rejection and retry recovery. | Purchase confirm/post/unpost/cancel rejection preservation passed 5/5 including setup. Sales invoice post/unpost/cancel failure-then-retry passed 4/4 including setup. Sales-note post, unpost, and cancel retry groups each passed 5/5 including setup, covering all four goods/service credit/debit note variants. | Purchase actions preserved Draft, Confirmed, or Posted state after rejected writes. Injected sales HTTP 500/409 responses surfaced actionable messages, preserved pre-action state, left the correct action enabled, and succeeded exactly once on retry. | Add 401/403/422/429 and timeout/disconnect/offline injection, then test interrupted upload/download recovery. |
| 15 September 2026 | Phase 6 | Completed cross-browser identity and provider recovery checks on the hardened staging build. | Login HTTP 500 plus GST lookup failure/retry passed 9/9 including setup across Chromium, Firefox, and WebKit; expired `/auth/me` plus failed refresh recovery passed 6/6 including setup across all three engines. | Failed login creates no session, provider retry succeeds without stale error state, and expired sessions land on the dedicated recovery page with retry and login actions. | Extend the same controlled 401/403/409/422/429/500/timeout/offline matrix to commercial write endpoints. |
| 15 September 2026 | Phase 6 | Closed the commercial HTTP, transport, and purchase-import recovery matrix on staging. | Existing bulk-print failure, offline-download retry, permission denial, and expired-session cases passed 4/4 including setup. A new 409/422/429 rejection-and-retry case passed in Chromium, Firefox, and WebKit. New interrupted purchase-upload and timed-out bulk-print cases passed 3/3 including setup in Chromium. With entity `2`, FY `2`, Head Office subentity `2`, and an existing stage vendor supplied through fixture environment variables, interrupted validation plus exactly-once commit and lost-response idempotent retry each passed 2/2 including setup; commit rejection and expired-session cases passed 3/3 including setup. | Rejections preserve route, filters, and enabled actions; actionable backend messages are shown; interrupted or timed-out requests can be resubmitted; failed commits create no documents; successful and lost-response retries retain one reconciliation result. | Move to print/export and accessibility certification; retain isolated-database concurrency, worker restart, provider callback, and infrastructure restore as Phase 6 dependencies. |
| 15 September 2026 | Phase 3 | Hardened staging security settings and completed the previously blocked Firefox/cross-browser taxability gate. | Release audit: 9 pass, 0 fail, 1 SMTP warning. Focused Firefox: 5/5 in 1.3 minutes. Final Chromium/Firefox/WebKit run: 15/15 in 3.4 minutes. | The original Firefox denial was not a tax or RBAC defect. Trace evidence showed a URL-only dashboard readiness check navigating away while an authentication refresh response was in flight; the server rotated the session but the browser never received the new cookie. The auth bootstrap now persists a quiet final context session, and the shared dashboard helper waits for a successful `/api/auth/me` response before continuing. | Execute controlled API failure/retry cases, document print/export accuracy, and automated/manual accessibility checks; prove SMTP delivery before public launch. |
| 14 September 2026 | Planning | Created P0 phase plan and combined P0/P1 portfolio gate. | Existing QA plans reviewed. | Baseline established. | Execute Phase 0 traceability inventory. |
| 14 September 2026 | Phase 0 | Captured machine inventories, classified domains, linked module evidence, and established event/cross-cutting traceability gates. | [P0 scope register](p0-core-launch-scope-traceability-register-2026-09-14.md) | Inventory baseline complete; formal scope freeze pending. | Approve classifications, owners, pilot profile, and production dependencies. |
| 14 September 2026 | Phase 1 | Verified the deployed Chromium authentication and workspace baseline using the active staging operator and `Manav-T`. | Playwright `auth-entity-integration.p0.spec.ts` and `entity-dashboard.p0.spec.ts`: 9/9 passed. | Login, entity entry, reload persistence, logout, protected-route blocking, cookie-session recovery, and dashboard load passed. | Run restricted-role isolation and Firefox/WebKit matrices; update the local Playwright credential profile. |
| 14 September 2026 | Phase 1 | Completed Firefox/WebKit identity checks and audited the proposed restricted account across its memberships. | Firefox/WebKit `auth-entity-integration.p0.spec.ts`: 12/12 passed; live role discovery showed `Entity Super Admin` in all three available entities. | Cross-browser identity passed. Negative RBAC remains blocked because the supplied account is privileged, not restricted. | Provision dedicated read-only/restricted memberships and run route, menu, action, API, export, and cross-entity denial matrices. |
| 14 September 2026 | Phase 1 | Activated the existing QA-only restricted fixture on `Manav-T` without changing customer users or roles, then certified browser and backend denial paths. | Chromium route matrix 27/27; `restricted-rbac-staging-live.p0.spec.ts` passed in Chromium, Firefox, and WebKit. | Restricted menus, purchase list/create, purchase register/export, payroll readiness, and foreign-entity permissions are denied; authorized home access remains available. | Expand to branch-scoped personas, object-level access, attachments, print/download, and background jobs. |
| 14 September 2026 | Phase 1 | Ran live provisioned-role matrices for branch scope, master mutations/exports, purchase workflow duties, HRMS view-only access, and employee/manager leave approval. | Targeted `admin-restricted-rbac-provisioned.p1.spec.ts` runs passed 5/5 and 3/3 including setup. Stage hygiene check found zero active temporary QA roles or assignments. | Assigned-branch access works while foreign-branch and entity-wide aggregation are denied; barcode export, imports, and bulk-print job creation are denied to view-only roles; operator, accountant, approver, and reporting permissions remain separated. | Add salary/bank/tax/payslip object checks and attachment authorization, then proceed to failure and concurrency isolation. |
| 14 September 2026 | Phase 1 | Added and executed a two-employee ESS payslip isolation regression. | Targeted Django test passed on PostgreSQL; list isolation plus foreign detail/PDF 404 assertions passed. | Payslip document ownership is enforced by linked employee user. Existing `sales.0048` SQL prevents the SQLite test profile from creating a fresh database. | Complete remaining sensitive payroll objects and track SQLite migration portability as test-infrastructure debt. |
| 14 September 2026 | Phase 1 | Closed an attachment authorization gap across payment, receipt, cash/bank/journal voucher endpoints and strengthened purchase/sales attachment scope checks. | Seven focused PostgreSQL regressions passed: real outsider list/download/delete denials for purchase and sales attachments, branch-aware payment/receipt/voucher authorization, payroll permission mapping, and ESS cross-employee payslip isolation. | Attachment operations now derive entity, FY, and branch from the parent document, validate any supplied branch against that parent, enforce subscription/scope, and require the matching view/create/delete action. | Run the wider module regression set, then verify the deployed behavior on staging after check-in. |
| 14 September 2026 | Phase 1 | Completed the wider access-control regression and repaired branch composition for sensitive payroll setup objects, payroll runs, reports, posting views, FnF, and payment-batch actions. | 91/91 PostgreSQL tests passed across payroll hardening/runtime transitions, payment, receipt, voucher, purchase/sales attachments, profiles, salary assignments, tax declarations, native tax inputs, and ESS payslips; Django system check passed. | Permissions from one branch cannot combine with scope from another. Sensitive profile data and operational payroll read/action paths now resolve permissions in the same branch as the protected object. | Check in and deploy, then repeat the browser/API denial matrix on the unchanged staging build before closing Phase 1. |
| 14 September 2026 | Phase 1 | Repeated the access-control gate against the deployed staging build with explicit staging credentials and entity scope. | `restricted-rbac-staging-live.p0.spec.ts`: 2/2 including setup in Chromium and 4/4 including setup in Firefox/WebKit; targeted provisioned branch, HRMS viewer, and ESS scenarios: 4/4 including setup in Chromium. | Restricted menus/APIs/exports/payroll and foreign-entity requests remained denied across all browser engines. Assigned-branch access worked while foreign-branch and entity-wide requests were denied; HRMS view-only and employee/manager boundaries remained intact. | Add a valid-parent staging probe for payment, receipt, voucher, purchase, and sales attachment list/download/delete authorization, then begin failure and concurrency isolation. |
| 14 September 2026 | Phase 1 | Exercised attachment authorization against real staging documents with a provisioned zero-permission tenant member. | `FIN-ATTACHMENT-RBAC-001`: 2/2 including setup passed in Chromium; five disposable PDF attachments were created by the administrator and removed in failure-safe cleanup. | Purchase, sales, payment, receipt, and shared-voucher attachment list, upload, download, and delete operations each returned `403` to the restricted member while valid administrator operations succeeded. | Complete direct sensitive-payroll object probes, then begin failure and concurrency isolation. |
| 14 September 2026 | Phase 1 | Exercised direct sensitive-payroll reads and lifecycle actions against real staging objects with a provisioned zero-permission member. | `FIN-PAYROLL-RBAC-OBJECT-001`: two consecutive Chromium runs passed 2/2 including setup; fixture coverage was profile, salary assignment, payroll run, posting status, calculate action, and payment batch. | All exercised administrative endpoints returned `403`, and the unlinked member's ESS payslip list was empty. Tax declaration, published payslip, and FnF remain fixture-dependent staging gaps and are not represented as passed. | Seed the three missing sensitive fixtures, close their direct probes, then start Phase 6 failure and concurrency isolation. |
| 14 September 2026 | Phase 6 | Started failure and concurrency certification with payroll, the highest-sensitivity P1 lifecycle. | Six PostgreSQL transaction tests plus the broadened payroll regression passed 108/108; focused Angular recovery passed 48/48; Playwright server/network retry passed 15/15 across three engines. | Concurrent calculation, posting, payment-batch creation/payment, and reversal are serialized; failed posting rolls back; readiness errors recover without stale data or duplicate retry requests. | Deploy both codebases, repeat payroll recovery/concurrency on staging, then extend the same matrix to core accounting and commercial commits. |
| 14 September 2026 | Phase 6 | Deployed payroll locking/recovery changes and repeated the browser/API gate after refreshing Gunicorn. | Backend revision `7e5451e6`; Django system check clean; HTTPS 200; combined staging recovery/live suite 18/18 and post-restart live readiness 6/6 across Chromium, Firefox, and WebKit. | The deployed readiness and recovery contract passed. Staging transaction tests were deliberately not run against customer data because the application role cannot create an isolated Django test database. | Provision an isolated staging test database/role, then execute controlled concurrency there and extend failure injection to accounting and commercial commits. |
| 15 September 2026 | Phase 3 | Started the commercial baseline across sales, purchase, receivables, payables, payments, receipts, and banking. | Combined backend regression passed 1,062/1,062. Selected staging bank, purchase/payment, payables, receivables, and sales/receipt workflows pass in Chromium; the corrected sales super-flow passed 2/2 including setup in 49.8 seconds. | No application defect was found in the sales save investigation: the valid Ship To guard exposed an omitted test-fixture step, which is now explicit and asserted. The bank integrity rerun also confirmed its earlier failure was a local-versus-SSH harness configuration error. | Expand Phase 3 to the complete goods/service/note lifecycle and settlement permutation matrix, then repeat the critical selection in Firefox and WebKit. |
| 15 September 2026 | Phase 3 | Expanded staging reconciliation to goods/service invoices and credit/debit notes, and hardened the browser fixtures. | All 16 business reconciliation scenarios pass across bounded Chromium runs; the complete sales-note spec passed 7/7 including setup in 3.7 minutes. GST symmetry and lookup pagination passed 25/25 across all 12 sales/purchase document surfaces. | The service-account fixture now requires an explicitly sales-classified account head, registered-customer selection no longer scans every option, optional toast diagnostics are bounded to 500 ms, and summary Save has a duplicate-safe component fallback. A single oversized 17-test mixed process reached 15 passes before browser-runner starvation; Nginx evidence showed the eventual note writes and reads completed within seconds. | Split the launch command by specification process, then execute settlement/taxability/failure permutations and Firefox/WebKit coverage. |
| 15 September 2026 | Phase 3 | Executed the expanded AR/AP settlement and cross-browser taxability staging gates. | Sales settlement shapes passed 6/6, sales settlement policies passed 6/6, and AP payment reconciliation passed 5/5 in bounded Chromium runs. Taxability preservation passed all four document surfaces in Chromium and WebKit. | Firefox storage-state replay reached Access Restricted because the saved session was refresh-rotated and revoked. A fresh Firefox UI login and direct Sales Invoice navigation returned three successful `/api/auth/me` checks, isolating the failure to replay under insecure staging cookies. The staging release audit failed eight controls: `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, SSL redirect, session/CSRF/auth secure cookies, and HSTS; SMTP readiness remains a warning. | Harden staging configuration, restart the application, rerun Firefox taxability, then continue failure/concurrency and print/export certification. |
| 15 September 2026 | Phase 3 | Executed purchase-payment concurrency, retry, and scope-isolation staging checks. | `FIN-PUR-CHAIN-005..007` passed 4/4 including authentication in Chromium in 2.4 minutes. | Concurrent payment posting could not settle one supplier bill twice, retrying a successful post reused one settlement/history row, and payment/open-item reads did not leak across entity, financial-year, or branch scope. | Complete environment hardening and the Firefox rerun, then close remaining recovery and document-output gates. |
