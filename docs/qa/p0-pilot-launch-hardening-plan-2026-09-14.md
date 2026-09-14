# P0 Pilot And Launch Hardening Plan

Status: In progress

Last updated: 14 September 2026

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

Status: In progress; local Chromium identity/onboarding baseline passed, restricted-role and cross-browser gates remain

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

Status: Not started

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

Status: Not started

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

Status: Not started

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

Status: Not started

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

Status: Not started

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
| Identity, onboarding, RBAC, and isolation | Not started | - | Not assessed | - |
| Core accounting and close | Not started | - | Not assessed | - |
| Sales/AR and purchase/AP | Not started | Existing module evidence to consolidate | Not assessed | - |
| Inventory/manufacturing/assets | Not started | Existing module evidence to consolidate | Open pending rows | - |
| Statutory compliance/providers | Not started | Existing module evidence to consolidate | Not assessed | - |
| Failure, concurrency, and recovery | Not started | - | Not assessed | - |
| UX, browsers, mobile, and accessibility | Not started | Existing partial evidence | Manual review pending | - |
| Performance and repeatability | Not started | - | Not assessed | - |
| Deployment, monitoring, and support | Not started | - | Not assessed | - |
| Pilot decision | Pending | - | Not assessed | - |
| Public-launch decision | Pending | Requires pilot evidence | Not assessed | - |

## 9. Phase Update Log

| Date | Phase | Change | Evidence | Result | Next action |
| --- | --- | --- | --- | --- | --- |
| 14 September 2026 | Planning | Created P0 phase plan and combined P0/P1 portfolio gate. | Existing QA plans reviewed. | Baseline established. | Execute Phase 0 traceability inventory. |
| 14 September 2026 | Phase 0 | Captured machine inventories, classified domains, linked module evidence, and established event/cross-cutting traceability gates. | [P0 scope register](p0-core-launch-scope-traceability-register-2026-09-14.md) | Inventory baseline complete; formal scope freeze pending. | Approve classifications, owners, pilot profile, and production dependencies. |
