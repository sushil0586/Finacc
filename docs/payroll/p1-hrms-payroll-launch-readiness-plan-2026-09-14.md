# P1 HRMS And Payroll Launch Readiness Plan

Status: In progress; Phase 0 inventory complete, scope approval pending

Last updated: 14 September 2026

Parent roadmap: [Product Expansion Priority Roadmap](../product/product-expansion-priority-roadmap-2026-09-14.md)

Paired launch gate: [P0 Pilot And Launch Hardening Plan](../qa/p0-pilot-launch-hardening-plan-2026-09-14.md)

Source backlog: [HRMS And Payroll Product Backlog](hrms-payroll-product-backlog.md)

## 1. Objective

Make HRMS and payroll launch ready as one end-to-end customer product. A new customer must be able to configure the organization, onboard employees, capture time and leave, calculate and approve payroll, post it to finance, execute payment handoff, complete statutory operations, serve employees, and reconcile every amount without hidden database administration.

## 2. Existing Foundation

The plan builds on implemented foundations rather than replacing them:

- Payroll run lifecycle, calculation, submit, approve, post, payment handoff/reconciliation, and reversal contracts.
- Contract-native salary structures and calculation inputs.
- Safe formula/rule execution and calculation trace snapshots.
- PF, ESI, PT, LWF, and TDS projection/statutory engine foundations.
- Attendance and payable-day engine with supported proration methods.
- FnF calculation and persistence foundation.
- Effective-dated payroll ledger policy and component posting resolution.
- Existing backend tests, posting verification, onboarding documentation, and rollout runbook.

Known product gaps remain in guided onboarding, entity-facing accounting configuration, leave integration, full income-tax execution, gratuity, employee self-service, reimbursement, FnF operations, payment formats/provider integration, and complete launch certification.

## 3. Launch Scope Decision

Phase 0 must classify every capability as:

- `Launch required`: needed by the first supported customer profile.
- `Conditional`: enabled only for configured jurisdictions/policies.
- `Manual governed`: explicitly supported through a controlled input/approval path.
- `Unsupported`: prevented in the UI/API and documented.
- `Later vertical`: recruitment, performance, and learning unless separately approved.

The first launch should support a clearly declared customer profile instead of implying universal Indian payroll coverage.

## 4. Phase Plan

### Phase 0: Product Inventory, Customer Profile, And Traceability

Status: In progress; repository inventory and proposed customer profile complete, approvals pending

Working register: [P1 HRMS And Payroll Phase 0 Scope Register](p1-hrms-payroll-phase0-scope-traceability-register-2026-09-14.md)

Goal: define the supported HRMS/payroll product and remove uncertainty about placeholders or hidden setup.

Work:

- Inventory every HRMS/payroll route, menu, screen, field, API, model, service, scheduled task, report, export, permission, and automated test.
- Walk the complete implementation journey as platform operator, entity admin, HR admin, payroll processor, finance approver, manager, and employee.
- Identify placeholders, dead actions, backend-only controls, hardcoded behavior, missing menus, and setup requiring shell/admin access.
- Define initial customer profiles by headcount, pay frequency, state/jurisdiction, attendance source, statutory schemes, bank/payment method, and organization complexity.
- Build requirement-to-screen-to-API-to-posting-to-report-to-test traceability.
- Decide explicit launch scope for recruitment, performance, learning, gratuity, annual TDS, loans, reimbursements, and FnF.

Exit evidence:

- Every supported capability has an owner, acceptance scenario, and accounting/statutory impact.
- No launch-required setup depends on direct database or Django admin intervention.
- Product, payroll SME, accounting, engineering, and QA approve the initial customer profile.

### Phase 1: Guided Customer And Organization Setup

Status: In progress; scoped readiness UI and live staging payload are verified across Chromium, Firefox, and WebKit

Goal: let an operator configure a payroll-ready entity through the product.

Work:

- Create one readiness journey covering entity, legal registrations, locations, branches, departments, designations, cost centres, shifts, weekly offs, holidays, leave policies, attendance policy, pay groups, periods, numbering, and approval policy.
- Add GST/PAN/legal-data reuse where appropriate without coupling payroll readiness to GST registration.
- Add effective-dated entity-facing editors for payroll policies, statutory registrations/rules, ledger policy, component mappings, payment configuration, and document templates.
- Show prerequisite status, blocker reason, responsible role, and direct correction action.
- Support template adoption with preview, version, effective date, controlled override, and rollback.
- Prevent duplicate or overlapping effective-dated configuration.

Exit evidence:

- A fresh entity reaches `Payroll Ready` using only documented screens.
- Readiness blocks a run when a required policy, mapping, period, registration, approval, or bank setting is missing.
- Configuration changes are versioned, scoped, effective-dated, and audited.

### Phase 2: Employee And Employment Lifecycle

Status: Not started

Goal: maintain complete, effective-dated employee and employment records.

Work:

- Employee identity/contact, statutory IDs, bank details, emergency contacts, documents, and consent.
- Employment contract, joining/probation/confirmation, department/designation/location/manager, pay group, work calendar, and cost allocation.
- Transfer, promotion, salary revision, leave of absence, suspension where supported, resignation, termination, and rehire.
- Bulk import with preview, row validation, duplicate handling, partial-failure policy, retry, and audit manifest.
- Maker/checker approval for sensitive bank, salary, tax, and statutory changes.
- Employee master completeness and exception reports.

Exit evidence:

- Effective-dated changes produce the correct payroll behavior before, on, and after their effective dates.
- Restricted users cannot view or modify salary, bank, tax, identity, or documents outside their scope.

### Phase 3: Time, Attendance, Leave, And Payroll Inputs

Status: Not started

Goal: produce governed payable-day and variable-input data for each payroll period.

Work:

- Shift assignment, attendance capture/import/integration, corrections, regularization, overtime, late/half-day, holidays, weekly offs, and lock.
- Leave types, accrual/opening, entitlement, request/approval, balance ledger, paid/unpaid classification, encashment, carry-forward, and lapse policies.
- Connect approved leave balances and attendance events to the existing attendance/payable-day engine.
- Recurring and one-time earnings/deductions, arrears, bonus/incentive, reimbursements, loans/advances, recoveries, and manual inputs.
- Input cutoff, maker/checker approval, bulk import, exception dashboard, and source traceability.

Exit evidence:

- Attendance, leave, payable days, LOP, overtime, and input totals reconcile employee by employee.
- Locked inputs cannot change silently after payroll calculation or approval.
- Every manual override stores reason, evidence, actor, and approval.

### Phase 4: Salary, Calculation, Tax, And Statutory Configuration

Status: Not started

Goal: make payroll calculations configurable, explainable, and safe for the declared customer profile.

Work:

- Salary component catalog, semantic codes, taxable/statutory flags, structures, grades, assignments, revisions, formulas, rules, caps, rounding, and proration.
- Complete policy-driven rounding and supported recurring/one-time rule execution.
- Configure PF, ESI, PT, LWF, and other declared schemes by registration, jurisdiction, effective date, threshold, ceiling, slab, and contribution party.
- Implement the approved income-tax scope: declarations, evidence, regime, prior income, projections, monthly TDS, adjustments, and year-end outputs, or clearly govern a manual projection path.
- Implement approved gratuity and separation-tax scope or expose governed manual inputs with validation and approval.
- Provide per-employee calculation trace showing source, formula/rule, base, rate/slab, proration, cap, rounding, and result.

Exit evidence:

- Independent spreadsheets reproduce representative gross-to-net results within agreed rounding tolerance.
- Unsupported formulas/rules fail with actionable configuration errors.
- Effective-dated policy changes do not alter historical approved run snapshots.

### Phase 5: Payroll Run Operations And Controls

Status: Not started

Goal: provide a safe payroll processor workbench from draft to approved result.

Work:

- Create period/run, readiness check, employee selection, calculate, compare, exceptions, correction, recalculate, submit, approve/reject, and lock.
- Show employee-level and component-level variance against prior period and configurable thresholds.
- Prevent duplicate active runs, stale updates, repeated calculation races, and post-approval mutation.
- Support off-cycle, supplemental, arrear, correction, and final-settlement runs within declared scope.
- Require segregation of duties where configured.
- Generate payroll register, variance, exception, statutory, bank, costing, and approval packs from frozen snapshots.

Exit evidence:

- The same frozen inputs always produce the same run result.
- Invalid state transitions and out-of-scope users are rejected at API and UI layers.
- A rejected/corrected run retains complete version and approval history.

### Phase 6: Posting, Reversal, Payment, And Finance Reconciliation

Status: Not started

Goal: connect payroll results to finance and settlement without duplicate or unexplained balances.

Work:

- Entity-facing ledger policies and component posting mappings by branch, department, cost centre, project, and effective date.
- Posting preview with unmapped/invalid-account blockers.
- Post payroll expenses, employee payable, employer contributions, statutory liabilities, reimbursements, recoveries, loans/advances, and rounding.
- Govern reversal, correction, repost, closed-period, backdated, and partial-failure behavior.
- Generate approved bank-specific payment files or integrate a governed payment provider.
- Record payment acknowledgement, rejection, retry, cancellation, and bank reconciliation without duplicate settlement.
- Reconcile payroll register to journal, ledgers, liability schedules, payment batch, bank, and financial statements.

Exit evidence:

- Debit equals credit; payroll register equals posting; liability opening + movement - payment = closing.
- Reversal restores ledger and payable state exactly and remains traceable to the source run.
- Repeated payment callbacks or retries cannot duplicate payment or accounting entries.

### Phase 7: Employee, Manager, And Administrator Self-Service

Status: Not started

Goal: complete daily employee-facing and administrative workflows.

Work:

- Employee profile/document updates, attendance summary, regularization, leave, claims/reimbursements, tax declarations/evidence, payslips, annual tax documents, loans, and payroll queries.
- Manager approvals and team exception views within reporting scope.
- Employee-safe APIs that never expose another employee's salary, tax, bank, attendance, or documents.
- Administrator FnF workbench for resignation/termination inputs, leave/notice/gratuity/recovery, calculation, approval, posting, payment, statement, and acknowledgement.
- Notification, task, reminder, escalation, and status history.
- Mobile, low-width, keyboard, and screen-reader usable workflows.

Exit evidence:

- All launch-required self-service paths are functional; no placeholder action remains.
- Employees can view only their own information and managers only their authorized hierarchy.
- FnF statement, posting, payment, and employee status reconcile.

### Phase 8: Reports, Statutory Operations, Documents, And Audit

Status: Not started

Goal: make payroll operable and auditable after calculation.

Work:

- Payroll, employee, attendance, leave, input, variance, costing, bank advice, liability, payment, FnF, and reconciliation reports.
- Statutory contribution/deduction registers, challan/deposit tracking, return data, certificates/forms, correction history, and filing evidence for declared schemes.
- Payslip and annual/separation documents with entity branding, pagination, filenames, secure delivery, and batch generation.
- Drilldown from report/document to employee snapshot, rule, approval, posting, and payment evidence.
- Export permission, redaction, watermark where required, retention, and audit log.

Exit evidence:

- Reports, documents, statutory totals, payments, and GL reconcile to the approved run.
- 100/500/1,000-employee batches meet agreed generation and download budgets for supported scale.

### Phase 9: Security, Recovery, UX, Accessibility, And Scale Certification

Status: Not started

Goal: certify the complete product under realistic roles, failures, browsers, and volume.

Work:

- Execute platform operator, entity admin, HR admin, payroll maker, approver, finance, manager, employee, read-only, and restricted role matrices.
- Verify entity, branch, department, manager hierarchy, employee-object, pay-group, and period isolation.
- Inject duplicate submit, stale version, concurrency, timeout, offline, partial import, failed payment, failed posting, worker restart, and interrupted document generation.
- Run Chromium, Firefox, WebKit, desktop, tablet, mobile, keyboard-only, automated accessibility, and manual screen-reader critical workflows.
- Run representative headcount and concurrent user/load tests.
- Verify logs, metrics, alerts, sensitive-data masking, audit retention, backup/restore, runbook, and support diagnostics.

Exit evidence:

- No S1/S2 defect, tenant leak, salary/privacy exposure, duplicate payment/posting, or unexplained payroll difference.
- Three consecutive clean staging suites against an unchanged build.
- Performance, accessibility, browser, recovery, and support gates are signed.

### Phase 10: Customer Onboarding Rehearsal And Launch Decision

Status: Not started

Goal: prove the product with a complete customer-shaped rehearsal.

Work:

- Onboard a clean entity through the guided journey without database intervention.
- Import/configure representative employees, opening leave/loan values, attendance, salary, statutory, accounting, and payment data.
- Execute a shadow run against independently prepared expected results.
- Execute two consecutive payroll periods including joiner, leaver/FnF, salary revision, absence, overtime, reimbursement, loan recovery, statutory change, posting, payment, and reversal/correction.
- Obtain customer/operator usability feedback and close launch-blocking findings.
- Record supported profile, known limits, migration/cutover plan, support model, rollback plan, and approvals.

Exit evidence:

- Two periods reconcile from employee input through bank and GL with zero unexplained difference.
- Product, payroll SME, accounting, engineering, QA, security/operations, support, and pilot owner sign the launch matrix.

## 5. Mandatory Scenario Matrix

### Organization And Employment

- Single/multiple branch, department, location, pay group, cost centre, and manager hierarchy.
- Monthly and any other explicitly supported pay frequency.
- Joiner, mid-period joiner, probation/confirmation, transfer, promotion, revision, leave of absence, leaver, termination, rehire, and FnF.
- Registered and non-GST entities; GST must not incorrectly control payroll eligibility.

### Pay And Attendance

- Fixed, percentage, component-based, input, formula, rule/slab, cap/floor, taxable/non-taxable, and employer/employee components.
- Calendar, working, fixed-26, fixed-30, actual attendance, and manual payable-day methods where supported.
- Paid/unpaid leave, LOP, overtime, half-day, late deduction, holiday, weekly off, arrear, bonus, reimbursement, loan/advance, recovery, and rounding.

### Statutory And Tax

- PF/ESI threshold and ceiling boundaries, PT slabs/jurisdictions, LWF frequency, registration absent/present, effective-date change, and retro adjustment.
- Declared income-tax regimes, declarations, evidence, projection, prior income, monthly adjustment, joiner/leaver, and year-end/separation behavior in supported scope.

### Lifecycle And Failure

- Draft, calculated, submitted, approved, posted, payment pending, paid, rejected, reversed, corrected, locked, and closed-period states.
- Duplicate click/request, stale version, concurrent processor, partial import, missing policy/mapping, failed posting, failed bank file/provider, timeout, and retry.

## 6. Definition Of Launch Ready

P1 is launch ready only when:

- The initial supported customer profile is explicit and enforced.
- Guided setup reaches payroll readiness without hidden technical intervention.
- Two consecutive representative payrolls reconcile independently.
- Employee, statutory, payable, payment, posting, ledger, and financial-report totals agree.
- No launch-required screen or action is a placeholder.
- Role and object isolation protects salary, tax, bank, identity, attendance, and documents.
- Failure and retry behavior is atomic, idempotent, and diagnosable.
- Mobile, cross-browser, accessibility, volume, backup/recovery, observability, and support gates pass.
- No unresolved S1/S2 defect remains.
- Named business and technical owners sign the launch matrix.

## 7. P1 Launch Matrix

| Gate | Status | Evidence | Blocking gaps | Owner approval |
| --- | --- | --- | --- | --- |
| Product inventory and launch scope | In progress | [P1 Phase 0 scope register](p1-hrms-payroll-phase0-scope-traceability-register-2026-09-14.md) | Proposed profile and exclusions await approval | - |
| Guided customer setup | In progress | Deployed readiness and platform-navigation checks passed in Chromium, Firefox, and WebKit | Full fresh-entity journey and restricted-role certification remain | - |
| Employee lifecycle | Not started | Existing implementation/tests to inventory | Not assessed | - |
| Attendance, leave, and inputs | Not started | Attendance engine exists | Leave-ledger integration incomplete | - |
| Calculation and statutory rules | In progress | Calculation audit Phases 1-5 | Rounding, full TDS/gratuity scope decisions remain | - |
| Run operations and approvals | Not started | Workflow foundation exists | End-user certification pending | - |
| Posting, payment, and GL reconciliation | In progress | Posting foundation and verification exist | Entity editors and governed payment formats pending | - |
| ESS, reimbursements, and FnF operations | Not started | FnF engine foundation exists | Product workbenches/placeholders remain | - |
| Reports, documents, and statutory operations | Not started | Existing surfaces to inventory | Not assessed | - |
| RBAC, isolation, recovery, UX, and scale | In progress | Payroll route denial 6/6 plus live menu/API/cross-entity denial in Chromium, Firefox, and WebKit; provisioned HRMS viewer and employee/manager approval scenarios passed on Chromium; employee payslip, salary/bank/tax object, payroll run/report/posting/FnF, and payment-batch permission composition passed against PostgreSQL | A governed tax-evidence file repository is not implemented; recovery, scale, and staging verification of the latest fixes remain | - |
| Customer rehearsal | Pending | - | Prior phases incomplete | - |
| Launch decision | Pending | - | Prior phases incomplete | - |

## 8. Phase Update Log

| Date | Phase | Change | Evidence | Result | Next action |
| --- | --- | --- | --- | --- | --- |
| 14 September 2026 | Planning | Created P1 phase plan using existing payroll audits, workflows, onboarding docs, and backlog. | Existing foundation and gaps classified. | Baseline established. | Execute Phase 0 product inventory and customer-profile decision. |
| 14 September 2026 | Phase 0 | Inventoried APIs, screens, menus, tests, personas, and repository-visible placeholders; proposed a bounded first-customer profile. | [P1 Phase 0 scope register](p1-hrms-payroll-phase0-scope-traceability-register-2026-09-14.md) | Inventory complete; profile and exclusions require approval. | Begin Phase 1 guided-readiness design after scope approval. |
| 14 September 2026 | Phase 1 | Verified deployed readiness counts, employee correction actions, mobile empty state, platform navigation, and the unmocked scoped readiness response. | Playwright `payroll-onboarding-readiness.p1.spec.ts`, platform shell check, and `payroll-onboarding-staging-live.p1.spec.ts`: 6/6 including setup checks passed. | Deployed readiness slice is healthy for the active staging operator and `Manav-T`. | Certify a clean entity from setup through Payroll Ready, then run restricted-role and cross-browser matrices. |
| 14 September 2026 | Phase 1 | Repeated payroll readiness, live API, mobile accessibility, and Platform Operations navigation in Firefox and WebKit. | Targeted staging suite: 10/10 passed. | Cross-browser readiness slice passed. Proposed restricted user was verified as `Entity Super Admin`, so it cannot certify payroll denial paths. | Provision a genuinely restricted payroll user, then execute payroll route, menu, API, and sensitive-data denial tests. |
| 14 September 2026 | Phase 1 | Activated the existing QA-only restricted fixture and ran payroll route plus live API/menu/cross-entity denial checks. | Payroll routes 6/6; `restricted-rbac-staging-live.p0.spec.ts` passed in all three browsers. | Zero-payroll-access fixture cannot see payroll menus or call payroll readiness; foreign-entity access is denied. | Add HR/payroll persona matrix and employee/salary/bank/tax object-isolation coverage. |
| 14 September 2026 | Phase 1 | Exercised provisioned HRMS view-only and employee/manager personas against staging. | `FIN-HRMS-RBAC-VIEW-001` and `FIN-HRMS-RBAC-ESS-001` passed on Chromium; full targeted run passed 5/5 including setup. | HRMS viewers can inspect permitted masters but cannot mutate/import; employees can submit their own leave but cannot self-approve; a permitted manager can approve it. | Add salary assignment, bank detail, tax declaration, payslip, and attachment object-isolation cases. |
| 14 September 2026 | Phase 1 | Added an adversarial ESS payslip regression using two real employee payroll setups. | `PayrollProductizationApiTests.test_ess_payslip_endpoints_do_not_expose_another_employees_document` passed on the PostgreSQL test profile. | An employee list contains only their payslip; another employee's real detail and PDF URLs return 404. The SQLite test profile remains blocked by PostgreSQL-specific SQL in existing migration `sales.0048`. | Add salary assignment, bank detail, tax declaration, and attachment object-isolation cases; repair SQLite migration portability separately. |
| 14 September 2026 | Phase 1 | Repaired payroll profile permission composition so entity RBAC contract-profile and salary-assignment grants are recognized before legacy group fallback. | `test_contract_profile_permissions_are_resolved_from_entity_rbac` passed as part of the seven-test PostgreSQL authorization regression set. | `profile_view`, `profile_create`, and `profile_edit` now resolve from the established entity permission codes; valid scoped payroll users no longer depend on a legacy Django group. | Complete adversarial salary assignment, bank detail, and tax-document object-isolation coverage. |
| 14 September 2026 | Phase 1 | Closed cross-branch composition and read-authorization gaps for contract payroll profiles, salary assignments, tax declarations/lines, payroll runs, reports, posting, FnF, and payment batches. | Adversarial branch tests passed, followed by a 91/91 PostgreSQL regression including payroll hardening/runtime transitions and financial attachments; system check passed. | Nested HRMS contract or operational document branch is now the authorization scope. A role's permission in branch A cannot expose sensitive data or authorize payroll operations in branch B, and branch lists are data-filtered. Tax-evidence file upload remains a separate unimplemented product capability. | Deploy and certify these denial and action paths on staging, then begin recovery/concurrency and governed tax-evidence design. |
