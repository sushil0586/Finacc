# P0 Core Launch Scope And Traceability Register

Status: Phase 0 inventory baseline complete; business ownership and scope approval pending

Last updated: 14 September 2026

Parent plan: [P0 Pilot And Launch Hardening Plan](p0-pilot-launch-hardening-plan-2026-09-14.md)

Paired gate: [P1 HRMS And Payroll Launch Readiness Plan](../payroll/p1-hrms-payroll-launch-readiness-plan-2026-09-14.md)

## 1. Purpose

This register is the controlled entry point for P0 certification. It records what exists, what evidence already exists, and what must still be proved before the product may be described as pilot ready or launch ready.

Inventory counts below are machine-derived discovery evidence. They prove breadth and help detect omissions; they do not prove that an API, screen, posting, or report is correct.

## 2. Machine Inventory Baseline

| Surface | Inventory result | Interpretation |
| --- | ---: | --- |
| Backend application URL declarations | 1,222 across 30 application URL modules | API/route discovery baseline; aliases and parameterized paths still require workflow classification |
| Frontend route declarations | 328 across root, HRMS, and payroll routing modules | Navigation baseline; redirects and helper-generated routes are included |
| Backend automated tests | 5,642 test methods across 425 files | Broad service/API safety net; test intent and business assertions remain the governing evidence |
| Frontend unit tests | 8,543 `it()` specifications across 432 files | Broad component coverage; presence does not replace browser or accounting verification |
| Playwright declarations | 4,725 static `test()` declarations across 258 spec files | Browser-suite source baseline |
| Playwright project executions | 8,808 tests reported by `playwright test --list` | Project/browser-expanded inventory; not a claim that the full suite currently passes |

Largest backend route domains are reports (322), payroll (124), purchase (122), catalog (57), withholding (54), platform operations (51), HRMS (43), financial (39), GST reconciliation (39), entity (36), assets (34), capital distribution (34), payments (27), receipts (27), manufacturing (24), bank reconciliation/operations (38 combined), inventory operations (19), and vouchers (18).

## 3. P0 Domain Classification

| Domain | Launch classification | Existing evidence | Phase 0 assessment | Required certification owner |
| --- | --- | --- | --- | --- |
| Identity, signup, session, and password recovery | Supported | Backend/frontend tests and browser suites exist | Consolidate happy, denial, expiry, and recovery paths | Product, security, QA |
| Entity onboarding and platform operations | Supported | Platform implementation and browser coverage exist | Prove public/platform parity, default masters, edit lifecycle, and audit | Product, operations, QA |
| Tenant, entity, branch, subentity, and FY scope | Supported | Scope fixes and tests exist across modules | One negative matrix must cover every data-bearing domain | Security, engineering, QA |
| RBAC, menus, entitlements, and object actions | Supported | RBAC migrations/tests and browser suites exist | Reconcile menu, route guard, API permission, export, print, and background actions | Security, product, QA |
| Financial masters and vouchers | Supported | Financial service/API/browser coverage exists | Reconcile classifications, lifecycle, posting, reversal, locks, and audit | Accounting, QA |
| Financial statements and books | Supported | Report services and prior fixes exist | Certify branch/FY/date scope, opening/closing, drilldown, exports, and equations | Accounting, reporting, QA |
| Sales, AR, receipts, and allocations | Supported | Extensive API and Playwright coverage exists | Re-run source-to-tax-to-stock-to-GL-to-AR launch matrix | Sales SME, accounting, QA |
| Purchase, AP, payments, and allocations | Supported | [Purchase-to-Pay plan](purchase-to-pay-production-signoff-plan-2026-09-09.md) | Close remaining staging, browser, scale, and policy rows | Purchase SME, accounting, QA |
| Inventory and manufacturing | Conditional until open evidence closes | [Inventory/manufacturing plan](inventory-manufacturing-production-signoff-plan-2026-09-08.md) | Open master, valuation, execution, recovery, and release rows block full support | Operations SME, accounting, QA |
| Assets and depreciation | Supported for declared workflows | Backend/frontend/browser coverage exists | Reconcile acquisition through disposal and all location/branch scopes | Asset SME, accounting, QA |
| GST, TDS, TCS, e-invoice, and e-way bill | Conditional by configured provider and registration | Compliance tests and provider workflows exist | Certify declared transactions, provider failure/idempotency, and secret redaction | Tax SME, security, QA |
| Capital distribution and organization forms | Conditional by configured organization policy | [Capital distribution plan](organization-capital-distribution-development-certification-plan-2026-09-10.md) | Manual assistive review and owner approvals remain | Accounting, tax, QA |
| Banking and reconciliation | Supported baseline; advanced treasury excluded | Bank reconciliation routes/tests exist | Certify import, matching, clearing, reversal, and GL agreement | Treasury SME, accounting, QA |
| HRMS and payroll | Governed only by P1 | [P1 Phase 0 register](../payroll/p1-hrms-payroll-phase0-scope-traceability-register-2026-09-14.md) | Not inherited as launch ready from P0 | HR/payroll SME, accounting, QA |
| Recruitment, CRM, advanced procurement/O2C, consolidation, projects, and industry packs | Backlog | Roadmap only | Must not be implied by current launch messaging | Product |

## 4. Critical Business Event Contract

Every supported event must receive one traceability row before its module phase can pass. A row is complete only when all columns have a concrete reference.

| Event family | Source state proof | Journal proof | Subledger/settlement proof | Inventory/asset proof | Tax proof | Report proof | Reversal/retry proof |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sales invoice and note | Required | Required | AR/receipt/allocation | Stock and COGS when applicable | GST/TCS/TDS | Registers and statements | Required |
| Purchase invoice and note | Required | Required | AP/payment/allocation | Stock/asset when applicable | GST/ITC/RCM/TDS | Registers and statements | Required |
| Cash, bank, journal, contra | Required | Required | Allocation when applicable | N/A | Withholding when applicable | Books and statements | Required |
| Stock transfer/adjustment/count | Required | Required when value changes | N/A | Quantity, batch/location, valuation | Tax only if applicable | Stock and financial reports | Required |
| Manufacturing issue/output/scrap | Required | Required | N/A | Consumption, WIP, output, valuation | Tax only if applicable | Production, stock, P&L/BS | Required |
| Asset capitalization/depreciation/disposal | Required | Required | Payable/receipt when applicable | Asset register and accumulated depreciation | Tax when applicable | Asset and financial reports | Required |
| Statutory submission/payment | Required | Required | Liability/payment | N/A | Return/provider acknowledgement | Compliance and GL reports | Required |
| Payroll run/payment/FnF | P1 required | P1 required | Employee/statutory payable | N/A | Payroll statutory | Payroll and financial reports | P1 required |

The detailed row set will be maintained in the owning module plan or test manifest and linked back here. P0 may not pass on a route-only or screenshot-only reference.

## 5. Cross-Cutting Traceability Gates

| Gate | Required evidence | Current Phase 0 status |
| --- | --- | --- |
| Screen-to-API | Every supported command names the called endpoint and expected success/error states | Inventory available; mapping pending by phase |
| API-to-permission | Every read/write/export/print/background action has positive and negative role tests | Partial evidence; consolidated matrix pending |
| Scope isolation | Entity, branch, subentity, FY, employee/object scope applied consistently | Partial evidence; full negative matrix pending |
| Source-to-accounting | Every financial event has expected accounts, amounts, dimensions, date, and reversal | Partial module evidence; consolidated event register pending |
| Source-to-report | Operational, statutory, subledger, and financial totals agree | Partial module evidence; independent datasets pending |
| Failure safety | Timeout, retry, stale version, duplicate click, worker/provider failure are atomic/idempotent | Core primitives exist; launch injection suite pending |
| UX and accessibility | Every critical state works on declared browsers/viewports and assistive paths | Partial browser evidence; manual certification pending |
| Operations | Migration, rollback, backup/restore, telemetry, alerts, and support ownership | Launch rehearsal pending |

## 6. Launch Dependencies To Register

Before Phase 0 is approved, operations must name the owner and environment source for:

- Database, cache, queues/workers, scheduler, object/file storage, email, PDF generation, and static/frontend hosting.
- WhiteBooks and every other statutory or messaging provider enabled in the launch environment.
- Secrets, certificate renewal, DNS/TLS, backups, restore tooling, monitoring, alerts, and log retention.
- Seed/default-master jobs, migration order, idempotent release commands, and rollback constraints.
- Customer support, incident commander, accounting escalation, security escalation, and provider escalation.

No credential value belongs in this register or in browser/test artifacts.

## 7. Phase 0 Exit Checklist

| Item | Status | Blocking note |
| --- | --- | --- |
| Backend, frontend, and Playwright inventories captured | Complete | Counts are discovery evidence only |
| P0 domains classified | Complete for proposed scope | Product/accounting approval pending |
| Existing module evidence linked | Complete for currently known plans | Owners must confirm no private/offline evidence is missing |
| Critical event traceability template established | Complete | Event-level rows remain phase work |
| Supported/conditional/unsupported labels approved | Pending | Requires named product and SME approval |
| Dependencies and operational owners recorded | Pending | Required before Phase 9 and scope freeze |
| Defect/waiver policy approved | Pending | Policy exists in parent plan; sign-off absent |
| P0 scope frozen | Pending | Cannot freeze while conditional domains remain unapproved |

## 8. Phase 0 Decision

Phase 0 discovery inventory is complete enough to begin P0 Phase 1 and P1 Phase 1 planning, but P0 scope is not yet formally frozen. The immediate blockers are owner approval of classifications, a named infrastructure/provider register, and confirmation of the first pilot profile.

## 9. Update Log

| Date | Change | Result |
| --- | --- | --- |
| 14 September 2026 | Started Phase 1 local certification across authentication, session recovery, entity entry, public signup, authenticated add-entity, platform operations, report access, payroll readiness, and mobile navigation. | 91 focused backend tests passed; 143 focused frontend tests passed; combined Chromium runs produced 81 passes, 27 controlled skips, and one menu-name defect that was fixed and passed targeted rerun. Restricted-role, controlled mutation, cross-browser, and staging evidence remain open. |
| 14 September 2026 | Captured backend, frontend, unit-test, and Playwright inventory; classified core domains; established event and cross-cutting traceability gates. | Phase 0 inventory baseline complete; approvals pending. |
