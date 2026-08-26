# Finacc Release Validation Order Tracker

Date: 2026-08-21

## Scope Note

Current scope note from release review:

- `Subscriptions`: end-to-end complete
- Pending scope decisions:
  - `GST reconciliation`
  - `commerce`
  - `retail`
  - `sales legacy import`

## How To Use

This tracker starts from validation step `2` onward.

For each row, record:

- `Status`
- `Owner`
- `Evidence`
- `Blockers`
- `Decision Notes`

## Status Values

- `Not Started`
- `In Progress`
- `Passed`
- `Passed With Conditions`
- `Blocked`
- `Deferred`
- `Failed`

## Validation Order

| Step | Module / Area | What To Validate | Status | Owner | Evidence | Blockers | Decision Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | Platform and access | Auth, onboarding, entity scope, RBAC, protected routing, session behavior | `In Progress` | `TBD` | P0 auth/onboarding/RBAC suites exist; `test:launch-commercial-smoke` is defined | Live session-expiry and release-env proof still pending | Strong repo-backed starting position |
| 3 | Financial masters and posting foundation | Financial masters, static accounts, numbering, base config | `In Progress` | `TBD` | Financial-master routes and P2 coverage exist; static account settings and posting code are present | Numbering and posting chain still need live proof | Foundation appears mature but not fully signed off |
| 4 | Voucher stack | Receipt, payment, journal, bank, cash, shared voucher behavior | `In Progress` | `TBD` | Voucher routes exist; P0/P1 voucher evidence and payment signoff scripts exist | Live ledger validation still pending | One of the stronger validation tracks |
| 5 | Purchase | Invoices, notes, settings, statutory, print, legacy import | `In Progress` | `TBD` | Dedicated signoff scripts, deep P1 suites, UAT docs, statutory docs, import docs | Print/export and live-env signoff still pending | Strongest release-ready area |
| 6 | Sales | Invoices, notes, compliance, TCS, settings, print, bulk print, sales legacy import if approved | `In Progress` | `TBD` | Dedicated signoff scripts, deep P1/P2 suites, compliance and TCS coverage | Sales legacy import scope still pending; print/export still needs manual signoff | Strongest release-ready area |
| 7 | Commercial downstream checks | Purchase/sales to payables, receivables, and ledger reconciliation | `In Progress` | `TBD` | Smoke bundle already includes downstream reconciliation suites | Final report-parity proof still pending | Should be executed immediately after purchase and sales |
| 8 | Catalog and inventory ops | Product masters, propagation, transfer, adjustment, stock effects | `In Progress` | `TBD` | Catalog P2 suites and inventory P1 CRUD/report suites exist | Live stock-effect verification still pending | Good repo evidence, medium live risk |
| 9 | Manufacturing | Workspaces, lifecycle flow, reporting, quantity/cost validation | `In Progress` | `TBD` | Workspace routes, docs, and P1 manufacturing suites exist | Cost/quantity validation remains a live checkpoint | Functional breadth exists but needs business sanity check |
| 10 | Assets | Asset masters, purchase-to-asset, depreciation, report and ledger impact | `In Progress` | `TBD` | Asset docs and P1 asset purchase flow audit evidence exist | Depreciation and report/ledger signoff still pending | Medium-high confidence, live proof needed |
| 11 | Bank reconciliation | Import, matching, exceptions, voucher creation, downstream parity | `In Progress` | `TBD` | Dedicated module, strong P1 browser/API evidence, prior gap plan exists | Mutation-submit, reload persistence, downstream parity need explicit live closure | High-value, high-risk control area |
| 12 | Financial reports | Trial balance, ledger, P&L, balance sheet, daybook, cashbook | `In Progress` | `TBD` | Financial report browser, parity, integrity, and performance suites exist | Totals signoff and release-dataset performance still pending | Mature but final business signoff needed |
| 13 | Payables and receivables reports | Outstanding, aging, ledger statements, registers, drilldowns | `In Progress` | `TBD` | Strong P1 suites across browser, filters, drilldowns, integrity, and seeded data | Totals and live reconciliation signoff still pending | Mature reporting area |
| 14 | Compliance and GST | GST reports, compliance reports, TCS, GST-TDS, withholding, GST reconciliation only if approved | `In Progress` | `TBD` | GST/compliance/TCS suites and docs are strong | GST reconciliation scope pending; GST-TDS/withholding are thinner and need live proof | Split broad-ready areas from rollout/pilot areas |
| 15 | Payroll | Payroll RBAC, payroll core, runs, posting preview, reports | `In Progress` | `TBD` | `test:payroll` and `test:payroll-rbac` exist; payroll module/docs are strong | Live payroll run and posting readiness still pending | Strong code/docs, moderate E2E depth |
| 16 | HRMS | HRMS validation only if confirmed in release scope | `Needs Scope Decision` | `TBD` | Backend/frontend footprint exists but direct proof is lighter | Needs explicit release-scope confirmation | Validate only if included |
| 17 | Support and release controls | Observability, audit logging, rollback, hotfix path, support runbook | `Blocked` | `TBD` | Support-related apps exist, but repo evidence does not prove production readiness | Observability, rollback, and support workflow need explicit signoff | Biggest current non-functional blocker |
| 18 | Final go / no-go | Review blockers, accepted conditions, deferred scope, final decision | `Not Started` | `TBD` | Depends on steps `2` to `17` | Cannot start until critical blockers are resolved or explicitly accepted | Final executive checkpoint |

## Recommended Evidence By Step

| Step | Recommended Evidence |
| --- | --- |
| 2 | `test:launch-commercial-smoke`, screenshots, RBAC notes |
| 3 | Settings screenshots, posting notes, numbering behavior notes |
| 4 | `test:payment:signoff`, voucher report screenshots, ledger notes |
| 5 | `test:purchase:signoff`, print samples, statutory screenshots |
| 6 | `test:sales:signoff`, compliance screenshots, print samples |
| 7 | Reconciliation screenshots, ledger/report parity notes |
| 8 | Inventory CRUD evidence, propagation screenshots |
| 9 | Manufacturing workspace screenshots, cost/quantity notes |
| 10 | Asset workflow evidence, depreciation/report notes |
| 11 | Bank reco run screenshots, voucher creation notes, parity screenshots |
| 12 | Financial report screenshots, totals notes, regression report |
| 13 | Payables/receivables screenshots, totals notes |
| 14 | GST/compliance screenshots, export samples, TCS notes |
| 15 | `test:payroll-rbac`, `test:payroll`, payroll posting notes |
| 16 | HRMS scope note and validation screenshots |
| 17 | Error capture proof, rollback notes, support runbook review |
| 18 | Final meeting notes and release decision |

## Fast Dependency Rules

- Do not start `4` before `3` passes.
- Do not start `7` before both `5` and `6` pass.
- Do not start `12`, `13`, or `14` before `7` passes.
- Do not mark final `Go` until `17` passes.

## Release Notes

- `Subscriptions` are considered complete based on current release review and are intentionally excluded from the active execution order.
- `GST reconciliation`, `commerce`, `retail`, and `sales legacy import` require explicit scope decisions before they can be marked `Passed` or `Deferred`.
