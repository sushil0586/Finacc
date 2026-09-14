# P1 HRMS And Payroll Phase 0 Scope Register

Status: Inventory complete; proposed launch profile and exclusions require business approval

Last updated: 14 September 2026

Parent plan: [P1 HRMS And Payroll Launch Readiness Plan](p1-hrms-payroll-launch-readiness-plan-2026-09-14.md)

P0 dependency: [P0 Core Launch Scope And Traceability Register](../qa/p0-core-launch-scope-traceability-register-2026-09-14.md)

## 1. Phase 0 Decision

The repository contains a substantial HRMS/payroll product, not only a prototype. Payroll calculation, statutory configuration foundations, run lifecycle, posting, reversal, payment batches, payslips, admin FnF, attendance, leave, and employee contracts have real models, APIs, services, and tests.

It is not yet launch ready as a complete self-service HRMS/payroll product. Several employee workflows and operational integrations are explicitly placeholders, and the first supported customer profile has not yet received business approval.

## 2. Machine Inventory

| Surface | Result | Meaning |
| --- | ---: | --- |
| Backend HRMS route declarations | 43 | Organization, employment, attendance, leave, shifts, calendars, onboarding |
| Backend payroll route declarations | 124 | Setup, calculation, statutory, runs, posting, payment, reports, ESS, FnF |
| Frontend HRMS route declarations | 19 | 17 functional routes plus redirects/wildcard |
| Frontend payroll route declarations | 38 | 36 functional screens plus redirects/wildcard |
| Backend HRMS/payroll test methods | 364 across 43 files | Strong service/API foundation; launch scenarios still need consolidation |
| Frontend HRMS/payroll unit specs | 1,313 across 117 files | Includes canonical and legacy payroll component trees |
| Playwright HRMS/payroll declarations | 120 across 7 files | P0 RBAC plus P1 workflow, screen, accessibility, responsive, attendance, leave, and payroll suites |

## 3. Proposed Initial Customer Profile

This profile is intentionally bounded. It should be approved or amended before Phase 1 implementation is treated as committed scope.

| Dimension | Proposed launch support |
| --- | --- |
| Jurisdiction | India domestic employer |
| Organization | One legal entity with multiple branches, departments, locations, cost centres, and manager hierarchy |
| Workforce | Salaried employees and governed monthly payroll contracts |
| Scale | Up to 500 active employees initially; 1,000-employee generation remains a certification target, not an unproved promise |
| Currency | INR |
| Pay frequency | Monthly only for first launch |
| Pay design | Fixed, percentage, formula/rule, recurring, one-time, arrear, bonus, deduction, recovery, and approved manual input where configured |
| Time basis | Calendar/working/fixed-day/actual-attendance methods already supported and explicitly configured |
| Statutory | PF, ESI, PT, and LWF where registrations and effective-dated rules are configured |
| Income tax | Conditional until full annual TDS scenarios are independently certified; governed manual projection/adjustment may be used only if visibly approved |
| Payment | Generic governed export and reconciliation; bank-specific upload only after an approved format implementation |
| Employee service | Payslips and implemented HRMS leave paths; placeholder ESS functions are excluded until completed |
| GST relationship | Registered, unregistered, and non-GST entities are valid; GST status must not gate payroll eligibility |

Explicitly excluded from first launch: recruitment/ATS, performance management, learning, multicurrency payroll, cross-border payroll, contractor marketplace, direct bank execution, and unsupported statutory jurisdictions.

## 4. Persona And Journey Inventory

| Persona | Required launch journey | Current assessment |
| --- | --- | --- |
| Platform operator | Enable product, adopt templates, diagnose readiness, support customer without reading payroll data unnecessarily | Foundation present; operational role/privacy rehearsal pending |
| Entity administrator | Configure organization, permissions, policies, registrations, accounting, and payment settings | Multiple screens exist; unified guided readiness journey incomplete |
| HR administrator | Maintain employees, contracts, organization units, shifts, calendars, attendance, leave, changes, and separation | Broad implementation exists; effective-date and bulk/customer rehearsal pending |
| Payroll processor | Prepare inputs, calculate, inspect exceptions/traces, submit, correct, and recalculate | Strong run foundation; full two-period browser rehearsal pending |
| Payroll approver | Review variance, approve/reject, preserve segregation of duties | APIs/screens exist; role matrix and evidence pending |
| Finance approver | Validate mappings, post/reverse, hand off payment, reconcile GL and liabilities | Strong backend foundation; entity-facing setup and launch reconciliation pending |
| Manager | Review team attendance/leave/inputs within hierarchy | Leave paths exist; complete hierarchy/object-scope proof pending |
| Employee | View own profile, attendance, leave, tax, claims, payslips, and FnF status | Payslips/leave and tax summary partial; attendance, claims, and FnF are incomplete/placeholders |

## 5. Functional Surface Classification

| Capability | Classification | Repository evidence | Launch gap |
| --- | --- | --- | --- |
| Organization units, employees, contracts, shifts, calendars | Launch required | HRMS APIs/screens/tests | Fresh-entity guided journey and completeness certification |
| Attendance capture and daily/monthly processing | Launch required | APIs, screens, engine, tests | Real import ingestion and employee/manager workflow certification |
| Leave policy, accrual, balance ledger, request/approval | Launch required | APIs/screens/tests | Prove payroll LOP/payable-day integration and effective dates |
| Salary components, structures, assignments, formulas/rules | Launch required | Models/services/screens/tests | Independent calculation workbook and historical immutability proof |
| Payroll periods, readiness, runs, submit/approve | Launch required | Real APIs/screens and extensive tests | Two-period customer-shaped browser rehearsal |
| PF/ESI/PT/LWF | Conditional | Statutory models/rules/services/reports/tests | Jurisdiction/effective-date boundary certification |
| Income-tax declarations and TDS projection | Conditional/manual governed | Admin CRUD/approval and ESS read summary exist | Full annual tax/evidence/joiner/leaver/year-end scope not certified |
| Payroll posting and reversal | Launch required | Posting preview/validate/status/post/reverse services and tests | Entity editor, invalid mapping UX, closed-period and reconciliation proof |
| Payment batches | Launch required | Validate/approve/export/paid/failed/cancel APIs | Approved bank format absent; generic export only |
| Payslips | Launch required | Run and employee-safe list/detail/PDF APIs/screens | Branding, access, batch, pagination, filename, and scale certification |
| Admin FnF | Launch required for leavers | Calculate/recalculate/approve/post/pay/cancel and snapshot APIs | PDF is explicitly placeholder; employee status/acknowledgement missing |
| Employee attendance summary | Launch required | Reads latest stored summary when present | API is explicitly a placeholder boundary when no summary/workflow exists |
| Employee reimbursements/claims | Launch required for complete ESS | Placeholder endpoint and explanatory screen only | No claim model/API/attachment/approval/payroll lifecycle |
| Employee FnF portal | Launch required for complete ESS | Frontend returns a client-side placeholder | No employee-safe backend status/statement/acknowledgement journey |
| Attendance file import | Launch required when file import is offered | Validate/commit routes and batch model exist | Default placeholder mode accepts metadata without real file ingestion |
| Bank-specific upload | Conditional | Generic payment export exists | `BANK_UPLOAD_PLACEHOLDER` is not a production bank format |
| Legacy payroll import | Unsupported for launch unless completed | Service declares mapping unimplemented | Hide/prevent or implement with governed migration tooling |

## 6. Route And Menu Findings

- Canonical HRMS and payroll routing modules expose the major functional screens.
- The payroll fallback menu declares 26 administrator routes with permission mappings.
- The HRMS fallback menu exposes only a smaller five-screen administrative subset; remaining routes depend on RBAC menu data or direct navigation and must be verified for each role.
- A legacy payroll component tree remains alongside the canonical `src/app/payroll` implementation. Phase 1 must identify every redirect/reference and prevent users from reaching inconsistent duplicate screens.
- Route existence, menu visibility, route guard authorization, and API authorization require one shared role matrix; none may be inferred from another.

## 7. Explicit Placeholder Register

| Placeholder | Current behavior | Required disposition before launch |
| --- | --- | --- |
| ESS reimbursements | Authenticated endpoint returns disabled placeholder; UI explains future workflow | Build claim lifecycle or remove from supported menus/product claims |
| ESS attendance summary | Returns latest stored summary when available, otherwise placeholder response | Complete employee workflow/empty state and prove employee-object isolation |
| ESS FnF | Frontend synthesizes placeholder without backend workflow | Build employee-safe endpoint/statement/status or exclude visibly |
| FnF statement PDF | PDF labels itself as a placeholder generated from snapshots | Replace with approved final statement template |
| Attendance import | Default mode is `PLACEHOLDER`; result may report acceptance without file ingestion | Implement real validated ingestion or disable upload claims |
| Bank upload | Placeholder CSV format is selectable | Implement named bank format(s) or expose generic CSV only |
| Legacy payroll import | Service reports mapping is not implemented | Keep unavailable or complete with preview/rollback/audit |

## 8. Accounting And Reconciliation Contract

For each frozen payroll run and FnF settlement, certification must prove:

`Employee gross - employee deductions = employee net payable`

`Employee net payable total = approved payment batch total = paid/reconciled total`

`Employee deductions + employer contributions = statutory liability movement`

`Payroll register totals = journal totals = ledger balances = liability schedules = financial statement movement`

The trace must preserve entity, FY, branch, department/cost centre, employee, component, period, rule/policy version, source input, approval, posting entry, reversal entry, payment batch, and reconciliation evidence.

## 9. Phase 0 Exit Checklist

| Item | Status | Note |
| --- | --- | --- |
| APIs, frontend routes, tests, and browser suites inventoried | Complete | Machine-derived baseline recorded |
| Personas and journeys classified | Complete for proposed scope | Customer/product approval pending |
| Placeholder and hidden-setup risks identified | Complete for repository-visible markers | Browser walkthrough will continue in later phases |
| Proposed customer profile written | Complete | Headcount, TDS, payment, and ESS boundaries need approval |
| Launch-required versus conditional/backlog classification | Complete for proposed scope | Product/payroll SME approval pending |
| Menus and duplicate legacy routes reconciled | Pending | Phase 1 implementation task |
| Accounting owner approves event contract | Pending | Required before launch calculation fixtures are frozen |
| Phase 0 scope approved | Pending | Requires product, payroll SME, accounting, engineering, QA, and operations |

## 10. Immediate Phase 1 Work Order

1. Build one guided readiness checklist from organization setup through first runnable payroll period.
2. Reconcile canonical/legacy routes and ensure each permitted screen is visible from a role-correct menu.
3. Add entity-facing ledger policy, component mapping, payment configuration, and statutory prerequisite correction paths where missing.
4. Replace silent placeholder exposure with an explicit feature-state contract: implemented, disabled, or unsupported.
5. Create a clean-entity Playwright journey that stops at each missing prerequisite and resumes after correction.

## 11. Update Log

| Date | Change | Result |
| --- | --- | --- |
| 14 September 2026 | Began Phase 1 by aligning the payroll onboarding screen with the real readiness endpoint. Added aggregate setup counts, named employee exception rows, per-issue correction actions, scoped browser assertions, mobile overflow, and automated WCAG checks. Removed unsupported reconciliation/cutover claims from this screen. | 67 focused onboarding/API/facade unit tests passed; the broader 143-test guard/scope/frontend set passed; three readiness Chromium executions passed. Fresh-entity completion, entity-facing ledger configuration, restricted roles, Firefox/WebKit, and staging remain open. |
| 14 September 2026 | Inventoried HRMS/payroll routes and tests, classified personas and functions, proposed first-customer profile, and recorded explicit placeholders. | Phase 0 inventory complete; business approval pending. |
