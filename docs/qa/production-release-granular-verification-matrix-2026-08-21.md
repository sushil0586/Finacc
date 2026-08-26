# Finacc Production Release Granular Verification Matrix

Date: 2026-08-21

## Purpose

This document is the final production-release verification matrix for Finacc.

It converts module completion into release-gate verification points so that each module can be reviewed at granular level before production signoff.

## How To Use This Document

For each module:

1. verify setup and access prerequisites
2. verify core CRUD or transaction workflow
3. verify policy and configuration effects
4. verify posting, reconciliation, and downstream reports
5. verify failure handling and recovery behavior
6. record test evidence and release decision

## Release Status Scale

- `Ready`: verification passed for all release-critical points
- `Ready With Conditions`: primary release gates passed, but non-blocking gaps remain with explicit acceptance
- `Not Ready`: one or more release-critical points are open
- `Deferred`: module is not in current release scope

## Verification Evidence Types

- `Auto`: Playwright, backend tests, unit specs, or scripted checks
- `Manual`: explicit business or QA validation
- `Hybrid`: automation plus targeted manual verification

## Global Release Gates

These gates apply to every production release:

| Gate | Verify | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Environment readiness | Production env vars, DB migrations, storage, queues, and external integrations are correct | Hybrid | `TBD` |  |
| Auth and session | Login, logout, token/session renewal, route protection, unauthorized redirects | Auto + Manual | `TBD` |  |
| Scope integrity | Entity, branch, and financial-year scope resolve correctly across modules | Hybrid | `TBD` |  |
| RBAC | Role-based access and denial paths are validated for critical modules | Hybrid | `TBD` |  |
| Error handling | User-safe failures, audit logging, and rollback behavior are acceptable | Hybrid | `TBD` |  |
| Observability | Production logging, error capture, and support diagnostics are usable | Manual | `TBD` |  |
| Performance baseline | No release-critical regression on major transaction and report flows | Auto + Manual | `TBD` |  |
| Release rollback readiness | Rollback steps, data backout constraints, and hotfix path are documented | Manual | `TBD` |  |

## Module Verification Matrix

### Core Platform

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Authenticated shell loads and protected navigation works | Yes | Auto | `TBD` |  |
| Home, dashboard, and primary workspace routing work without broken redirects | Yes | Auto | `TBD` |  |
| Session expiry and unauthorized redirect behavior is safe | Yes | Hybrid | `TBD` |  |
| Unsaved-changes guards appear only where intended | No | Hybrid | `TBD` |  |
| Production menu visibility matches feature flags and permissions | Yes | Hybrid | `TBD` |  |

### Authentication

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Login with valid credentials succeeds | Yes | Auto | `TBD` |  |
| Invalid login is handled safely | Yes | Auto | `TBD` |  |
| Forgot-password flow works end to end | Yes | Hybrid | `TBD` |  |
| Register and verify-email flows behave correctly if enabled in production | Conditional | Hybrid | `TBD` |  |
| Logout fully clears protected access | Yes | Auto | `TBD` |  |

### Registration And Onboarding

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| New entity onboarding can complete required steps | Yes | Hybrid | `TBD` |  |
| Onboarding failure states are actionable and non-destructive | Yes | Manual | `TBD` |  |
| Post-onboarding landing and module access are correct | Yes | Hybrid | `TBD` |  |
| Re-entry after partial onboarding is safe | No | Manual | `TBD` |  |

### Entity Management

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Entity master data persists correctly | Yes | Hybrid | `TBD` |  |
| Entity scope propagates to transactions and reports | Yes | Hybrid | `TBD` |  |
| Cross-entity isolation is preserved | Yes | Hybrid | `TBD` |  |
| Entity-linked statutory setup prerequisites are valid | Yes | Manual | `TBD` |  |

### RBAC And Admin Access

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Admin user management works for create, update, disable | Yes | Hybrid | `TBD` |  |
| Role mapping grants intended access | Yes | Hybrid | `TBD` |  |
| Denied pages and hidden actions are blocked correctly | Yes | Hybrid | `TBD` |  |
| Permissions for report hubs and settings screens are correct | Yes | Hybrid | `TBD` |  |

### Geography And Localization

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Geographic masters required by commercial flows are valid | Yes | Manual | `TBD` |  |
| Localization defaults do not break tax, address, or statutory behavior | Yes | Manual | `TBD` |  |
| Dependent dropdowns and saved values are stable | No | Hybrid | `TBD` |  |

### Dashboard And Analytics

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Dashboard loads without console or API failure | Yes | Auto | `TBD` |  |
| Critical analytics links land on correct workspaces | Yes | Auto | `TBD` |  |
| Empty-state and no-data states are user-safe | No | Manual | `TBD` |  |
| Accessibility and layout remain usable for release-critical dashboards | No | Auto | `TBD` |  |

### Financial Masters

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Account types, heads, ledgers, and accounts can be created and edited | Yes | Hybrid | `TBD` |  |
| Duplicate prevention and validation rules behave correctly | Yes | Hybrid | `TBD` |  |
| Deactivation or edit propagation does not break consuming workflows | Yes | Hybrid | `TBD` |  |
| Scope rules by entity and branch hold correctly | Yes | Hybrid | `TBD` |  |

### Posting And Static Accounts

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Static account mapping is complete for enabled modules | Yes | Manual | `TBD` |  |
| Posted transactions generate expected ledger impact | Yes | Hybrid | `TBD` |  |
| Missing mapping fails safely with actionable feedback | Yes | Hybrid | `TBD` |  |
| Unpost and reversal behavior is consistent | Yes | Hybrid | `TBD` |  |

### Numbering

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Document numbering sequences are configured correctly | Yes | Manual | `TBD` |  |
| Concurrent save does not produce duplicate numbers | Yes | Hybrid | `TBD` |  |
| Module-specific numbering policies hold after reopen or edit | No | Hybrid | `TBD` |  |

### Voucher Shared Layer

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Shared voucher buttons and state transitions behave consistently | Yes | Auto | `TBD` |  |
| Confirm, post, unpost, cancel, and reopen paths are safe | Yes | Hybrid | `TBD` |  |
| Ledger impact and downstream report visibility are correct | Yes | Hybrid | `TBD` |  |
| Validation and message handling are operator-safe | Yes | Hybrid | `TBD` |  |

### Receipt Voucher

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Draft create and save works | Yes | Auto | `TBD` |  |
| Confirm, post, and unpost work cleanly | Yes | Auto + Hybrid | `TBD` |  |
| Customer allocation and reconciliation behavior is correct | Yes | Hybrid | `TBD` |  |
| Receipt impact appears in receivables and ledger outputs | Yes | Hybrid | `TBD` |  |
| Reopen, refresh, and repeat-save stability is acceptable | No | Auto | `TBD` |  |

### Payment Voucher

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Draft create and save works | Yes | Auto | `TBD` |  |
| Confirm, post, and unpost work cleanly | Yes | Hybrid | `TBD` |  |
| Vendor settlement and outstanding reduction are correct | Yes | Hybrid | `TBD` |  |
| Payment impact appears in payables and ledger outputs | Yes | Hybrid | `TBD` |  |
| Advanced payment settings and operator controls behave correctly | No | Auto + Manual | `TBD` |  |

### Journal Voucher

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Entry balancing and validation rules are enforced | Yes | Hybrid | `TBD` |  |
| Post and unpost ledger correctness is validated | Yes | Hybrid | `TBD` |  |
| Manual adjustment visibility in reports is correct | Yes | Manual | `TBD` |  |

### Bank Voucher

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Bank voucher create, post, unpost is valid | Yes | Hybrid | `TBD` |  |
| Bank ledger and cashbook visibility are correct | Yes | Hybrid | `TBD` |  |
| Bank-specific validation and account constraints behave correctly | Yes | Manual | `TBD` |  |

### Cash Voucher

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Cash voucher create, post, unpost is valid | Yes | Hybrid | `TBD` |  |
| Cashbook visibility and cash control behavior are correct | Yes | Hybrid | `TBD` |  |
| Cash account restrictions and validations are correct | Yes | Manual | `TBD` |  |

### Purchase Invoices And Notes

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Purchase invoice and note create, edit, confirm, post, unpost work correctly | Yes | Auto + Hybrid | `TBD` |  |
| Tax, bill period, line mode, and policy-driven behavior are correct | Yes | Auto + Hybrid | `TBD` |  |
| Vendor outstanding, register, and downstream reconciliation are correct | Yes | Hybrid | `TBD` |  |
| Refresh, reopen, duplicate-save, and draft-resync behavior is stable | Yes | Auto | `TBD` |  |
| Blocking validations are correct for missing vendor, lines, or tax context | Yes | Auto | `TBD` |  |

### Purchase Statutory

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Purchase statutory workspace loads with correct scope | Yes | Hybrid | `TBD` |  |
| Filters, totals, and classification outputs are correct | Yes | Hybrid | `TBD` |  |
| Report drilldowns reconcile with purchase source data | Yes | Hybrid | `TBD` |  |
| Export or print outputs are correct if release-scoped | Conditional | Manual | `TBD` |  |

### Purchase Settings And Charge Types

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Purchase settings save and apply correctly | Yes | Hybrid | `TBD` |  |
| Charge types appear and behave correctly in purchase transactions | Yes | Hybrid | `TBD` |  |
| Settings toggles do not break existing transactions | Yes | Hybrid | `TBD` |  |

### Purchase Print And Exports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Purchase print launches correctly for eligible documents | Yes | Auto + Manual | `TBD` |  |
| Purchase note print works correctly | Yes | Auto + Manual | `TBD` |  |
| Exported output content and formatting are acceptable | Conditional | Manual | `TBD` |  |

### Purchase Legacy Import

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Import file acceptance and validation are correct | Yes | Hybrid | `TBD` |  |
| Imported data lands in expected purchase workflow state | Yes | Hybrid | `TBD` |  |
| Invalid rows fail safely with actionable diagnostics | Yes | Manual | `TBD` |  |

### Sales Invoices And Notes

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Sales invoice and note create, edit, confirm, post, unpost work correctly | Yes | Auto + Hybrid | `TBD` |  |
| Tax, service/product mode, shipping, and customer context behavior are correct | Yes | Auto + Hybrid | `TBD` |  |
| Receivables, register, and downstream reconciliation are correct | Yes | Hybrid | `TBD` |  |
| Button states and save-state transitions are stable | Yes | Auto | `TBD` |  |
| Draft reopen, refresh, and confirmed-state policies hold | Yes | Auto | `TBD` |  |

### Sales Compliance

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Compliance actions appear only for eligible posted documents | Yes | Auto + Manual | `TBD` |  |
| Payload generation and action dialogs are correct | Yes | Auto + Hybrid | `TBD` |  |
| IRN and compliance artifacts show correct state after post | Yes | Hybrid | `TBD` |  |
| Non-applicable documents show safe, correct fallback behavior | Yes | Auto | `TBD` |  |

### Sales TCS

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| TCS policy and calculation behavior are correct | Yes | Auto + Hybrid | `TBD` |  |
| Zero-collection and non-application reasons are preserved correctly | Yes | Auto + Hybrid | `TBD` |  |
| TCS browser, statutory, and exports reconcile with source documents | Yes | Hybrid | `TBD` |  |

### Sales Settings And Charge Types

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Sales settings save and apply correctly | Yes | Hybrid | `TBD` |  |
| Charge types appear and behave correctly in sales transactions | Yes | Hybrid | `TBD` |  |
| Settings toggles do not break existing sales documents | Yes | Hybrid | `TBD` |  |

### Sales Bulk Print

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Bulk print center loads and filters correctly | Conditional | Hybrid | `TBD` |  |
| Eligible documents are printed/exported correctly | Conditional | Manual | `TBD` |  |

### Sales Legacy Import

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Import route is usable and role-accessible | Conditional | Hybrid | `TBD` |  |
| Imported sales data enters the expected workflow state | Conditional | Hybrid | `TBD` |  |

### Catalog And Product Masters

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Product master create, edit, deactivate works correctly | Yes | Hybrid | `TBD` |  |
| HSN/SAC, UOM, price list, taxability, and account mapping are valid | Yes | Hybrid | `TBD` |  |
| Product changes propagate correctly into sales and purchase flows | Yes | Hybrid | `TBD` |  |
| Deactivated items are blocked safely where required | Yes | Hybrid | `TBD` |  |

### Inventory Operations

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Inventory transfers create and list correctly | Yes | Hybrid | `TBD` |  |
| Inventory adjustments create and list correctly | Yes | Hybrid | `TBD` |  |
| Location master behavior and permissions are valid | Yes | Hybrid | `TBD` |  |
| Stock movement effects propagate to downstream reports | Yes | Hybrid | `TBD` |  |

### Inventory Reporting

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Inventory report shells load under proper scope | Yes | Auto | `TBD` |  |
| Filters, totals, and drilldowns are correct | Yes | Hybrid | `TBD` |  |
| Cross-report consistency for inventory data holds | Yes | Hybrid | `TBD` |  |
| Performance for larger data states is acceptable | No | Auto + Manual | `TBD` |  |

### Manufacturing Workspaces

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| BOM and route maintenance works correctly | Yes | Hybrid | `TBD` |  |
| Work order create and lifecycle actions work correctly | Yes | Hybrid | `TBD` |  |
| Permissions and settings required for manufacturing are valid | Yes | Manual | `TBD` |  |
| Inventory and costing side-effects are acceptable | Yes | Hybrid | `TBD` |  |

### Manufacturing Reporting And Reconciliation

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Manufacturing report shells and filters work | Yes | Hybrid | `TBD` |  |
| Reconciliation drilldowns map correctly to source activity | Yes | Hybrid | `TBD` |  |
| Cost and quantity outputs are acceptable for release scope | Yes | Manual | `TBD` |  |

### Assets / Fixed Assets

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Asset category and asset master maintenance works | Yes | Hybrid | `TBD` |  |
| Purchase-to-asset flow works if enabled | Yes | Hybrid | `TBD` |  |
| Depreciation run behavior is correct | Yes | Hybrid | `TBD` |  |
| Asset events, history, and location/custodian outputs are correct | Yes | Hybrid | `TBD` |  |
| Ledger and report impact is validated | Yes | Hybrid | `TBD` |  |

### Bank Reconciliation

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Import preview, validate, and workspace handoff works | Yes | Hybrid | `TBD` |  |
| Auto-match and manual match flows submit correctly | Yes | Hybrid | `TBD` |  |
| Group match, partial match, unmatch, and exception actions work | Yes | Hybrid | `TBD` |  |
| Voucher creation from bank line works and reconciles correctly | Yes | Hybrid | `TBD` |  |
| Run actions, reload persistence, and downstream reports are correct | Yes | Hybrid | `TBD` |  |

### Financial Hub Reports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Trial balance, ledger, profit and loss, balance sheet, trading account load correctly | Yes | Auto + Hybrid | `TBD` |  |
| Filters, search, scope changes, and drilldowns behave correctly | Yes | Auto + Hybrid | `TBD` |  |
| Totals and report parity are acceptable | Yes | Hybrid | `TBD` |  |
| Report performance is within acceptable baseline | Yes | Auto + Manual | `TBD` |  |

### Payables Reports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Vendor outstanding, AP aging, ledger statement, register load correctly | Yes | Auto + Hybrid | `TBD` |  |
| Drilldowns, pagination, and scope persistence work correctly | Yes | Auto + Hybrid | `TBD` |  |
| Totals reconcile with purchase and payment activity | Yes | Hybrid | `TBD` |  |

### Receivables Reports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Customer outstanding, aging, ledger statement, register load correctly | Yes | Auto + Hybrid | `TBD` |  |
| Drilldowns, actions, filters, and scope persistence work correctly | Yes | Auto + Hybrid | `TBD` |  |
| Totals reconcile with sales and receipt activity | Yes | Hybrid | `TBD` |  |

### Compliance Reports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Compliance report shells load correctly | Yes | Auto | `TBD` |  |
| Filters, tabs, and drilldowns work correctly | Yes | Hybrid | `TBD` |  |
| Live data changes from source transactions appear correctly | Yes | Hybrid | `TBD` |  |
| Filing-readiness and exception outputs are acceptable | Yes | Manual | `TBD` |  |

### GST Reports

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| GSTR-1, GSTR-3B, and GSTR-9 report flows load and filter correctly | Yes | Hybrid | `TBD` |  |
| Totals and classification buckets are acceptable | Yes | Hybrid | `TBD` |  |
| Export behavior is correct if in release scope | Conditional | Manual | `TBD` |  |

### GST Reconciliation

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Reconciliation dashboard and run detail access works | Yes | Hybrid | `TBD` |  |
| Import, match, review, and issue workflows are correct for enabled scope | Yes | Hybrid | `TBD` |  |
| Performance and supportability are acceptable for release data volume | Yes | Manual | `TBD` |  |
| Pilot-only restrictions are explicit if not full-production ready | Yes | Manual | `TBD` |  |

### GST-TDS

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| GST-TDS configuration screen access and save works | Yes | Hybrid | `TBD` |  |
| GST-TDS report or dependent outputs are correct | Yes | Hybrid | `TBD` |  |

### TCS Configuration And Filing

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| TCS sections, rules, party profiles, and config save correctly | Yes | Hybrid | `TBD` |  |
| TCS statutory workspace and filing-related outputs are correct | Yes | Hybrid | `TBD` |  |
| TCS policy changes propagate to source and report flows correctly | Yes | Hybrid | `TBD` |  |

### Withholding

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Withholding master/config behavior works correctly | Yes | Hybrid | `TBD` |  |
| Dependent posting and reporting chains are correct | Yes | Hybrid | `TBD` |  |

### Payroll Core

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Payroll masters, periods, and runs load correctly | Yes | Hybrid | `TBD` |  |
| Payroll run lifecycle and run detail behavior is correct | Yes | Hybrid | `TBD` |  |
| Payroll permissions and onboarding constraints are valid | Yes | Manual | `TBD` |  |
| Payroll posting preview and posting readiness are acceptable | Yes | Hybrid | `TBD` |  |

### Payroll ESS

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| ESS pages load correctly for eligible users | Yes | Hybrid | `TBD` |  |
| Payslips, tax declarations, reimbursements, and attendance flows behave correctly | Yes | Hybrid | `TBD` |  |
| Access denial for non-eligible users is correct | Yes | Manual | `TBD` |  |

### Payroll Approvals And Policies

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Approval inbox and approval actions work correctly | Yes | Hybrid | `TBD` |  |
| Policy and approval configuration persists and applies correctly | Yes | Hybrid | `TBD` |  |

### Payroll Reporting And Posting

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Payroll reports load correctly | Yes | Hybrid | `TBD` |  |
| Payroll posting verification is acceptable | Yes | Hybrid | `TBD` |  |
| Runtime readiness signals are acceptable | Yes | Manual | `TBD` |  |

### HRMS

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| HRMS pages needed in this release load correctly | Conditional | Hybrid | `TBD` |  |
| Attendance or employee workflows needed in release scope work correctly | Conditional | Hybrid | `TBD` |  |

### Commerce

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Commerce routes enabled in production are reachable and safe | Conditional | Hybrid | `TBD` |  |
| Promotion or line-tester flows do not break shared sales behavior | Conditional | Hybrid | `TBD` |  |

### Retail

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Retail sale entry works if included in production scope | Conditional | Hybrid | `TBD` |  |
| Retail posting and downstream report behavior is correct | Conditional | Hybrid | `TBD` |  |

### Subscriptions

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Subscription features in current release are explicitly identified | Yes | Manual | `TBD` |  |
| Any enabled subscription behavior is production-safe | Conditional | Manual | `TBD` |  |

### Invoice Import

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Enabled import routes are role-accessible and stable | Yes | Hybrid | `TBD` |  |
| Upload, validate, and land-in-workflow behavior is correct | Yes | Hybrid | `TBD` |  |

### Inventory And Manufacturing Admin Surfaces

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Settings screens save correctly | Yes | Hybrid | `TBD` |  |
| Settings changes propagate correctly to dependent workflows | Yes | Hybrid | `TBD` |  |

### Audit Logging

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Critical transaction actions are audit-visible where required | Yes | Manual | `TBD` |  |
| Audit entries contain usable operator context | Yes | Manual | `TBD` |  |

### Error Logging

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Critical application failures are captured | Yes | Manual | `TBD` |  |
| Support team can correlate errors to user actions | Yes | Manual | `TBD` |  |

### Helpers And Core Support Libraries

| Verification Point | Release Critical | Evidence Type | Status | Notes |
| --- | --- | --- | --- | --- |
| Shared utility changes do not introduce regressions in critical modules | Yes | Auto + Hybrid | `TBD` |  |
| No known shared-library blocker remains open for production | Yes | Manual | `TBD` |  |

## Suggested Execution Order

1. Global release gates
2. Auth, onboarding, entity, RBAC
3. Financial masters, posting, numbering
4. Voucher stack
5. Purchase stack
6. Sales stack
7. Catalog, inventory ops, manufacturing, assets
8. Bank reconciliation
9. Financial, payables, receivables, and compliance reports
10. GST, TCS, GST-TDS, withholding
11. Payroll and HRMS
12. Lower-scope modules: commerce, retail, subscriptions
13. Audit, observability, rollback, final signoff

## Production Signoff Summary

| Area | Owner | Status | Blocking Issues | Go / No-Go Notes |
| --- | --- | --- | --- | --- |
| Platform | `TBD` | `TBD` |  |  |
| Commercial core | `TBD` | `TBD` |  |  |
| Inventory and manufacturing | `TBD` | `TBD` |  |  |
| Reporting and compliance | `TBD` | `TBD` |  |  |
| Payroll and HRMS | `TBD` | `TBD` |  |  |
| Support and observability | `TBD` | `TBD` |  |  |

## Current Audit Position

This section is the current repo-evidence assessment as of 2026-08-21.

Important:

- these are not full live-production signoffs
- these statuses are based on code, routes, docs, automation coverage, and existing test-result artifacts
- any point marked `Manual` or `Hybrid` still needs execution evidence before final go-live approval

### Current Area Status

| Area | Current Assessment | Why | What Still Must Happen Before Final Signoff |
| --- | --- | --- | --- |
| Platform | Ready With Conditions | Strong auth, onboarding, routing, and RBAC coverage exists, including dedicated smoke and P0 flows | Live env validation for session expiry, env config, and unauthorized behavior |
| Commercial core | Ready With Conditions | Purchase, sales, vouchers, payment, receipt, and reconciliation-linked flows have the strongest route and automation evidence | Final live rerun of commercial smoke, posting validation, and report parity checks |
| Inventory and manufacturing | Ready With Conditions | Real module depth exists with P1/P2 browser coverage and docs | Live transaction-to-report validation and costing sanity check |
| Reporting and compliance | Ready With Conditions | Financial, payables, receivables, GST, and compliance suites are broad and mature | Final filter/export/totals signoff in live production-like data |
| Payroll and HRMS | Ready With Conditions | Payroll code and docs are strong; HRMS exists but is lighter | Live payroll run, ESS, approval, and posting readiness validation |
| Support and observability | Not Ready | Support modules exist, but current repo evidence does not prove production logging, alerting, and rollback readiness | Explicit observability, rollback, and support-runbook validation |

### Current Module Status

| Module | Current Assessment | Basis | Remaining Release Risk |
| --- | --- | --- | --- |
| Core platform | Ready With Conditions | Protected routing, auth guards, dashboard shell, onboarding flows, and smoke coverage exist | Live environment behavior still needs validation |
| Authentication | Ready With Conditions | P0 auth coverage and dedicated login/forgot-password UI exist | Password reset and token/session lifecycle need live proof |
| Registration and onboarding | Ready With Conditions | Registration/onboarding P0 coverage and frontend/backend structure are present | Production policy and partial-onboarding recovery need manual signoff |
| Entity management | Ready With Conditions | Large backend app and entity-linked workflows exist | Scope and setup dependencies need live cross-module validation |
| RBAC and admin access | Ready With Conditions | Strong backend presence and report-access test evidence | Permission drift remains a production risk without explicit role-matrix pass |
| Geography and localization | Needs Live Verification | Supporting backend exists, but direct E2E proof is light | Locale, address, and statutory dependency checks |
| Dashboard and analytics | Ready With Conditions | Browser, accessibility, and link tests exist | Live API and empty-state sanity check |
| Financial masters | Ready With Conditions | Route coverage, specs, and downstream module dependency depth are strong | Final CRUD, duplicate, and propagation pass in live env |
| Posting and static accounts | Ready With Conditions | Strong backend implementation and settings coverage exist | Live posting-chain validation is still critical |
| Numbering | Needs Live Verification | Important backend support exists, but low direct automated proof | Concurrency and sequence correctness need explicit testing |
| Voucher shared layer | Ready With Conditions | P0/P1 voucher coverage and downstream reconciliation evidence exist | Full post/unpost regression rerun needed |
| Receipt voucher | Ready With Conditions | Dedicated P0/P1 evidence plus service-backed backend module | Live receivable reconciliation and report propagation check |
| Payment voucher | Ready With Conditions | Dedicated payment scripts and P1 depth exist | Live settlement-chain and payable impact validation |
| Journal voucher | Ready With Conditions | Shared voucher behavior and routing are mature | Journal-specific ledger validation still needs manual pass |
| Bank voucher | Ready With Conditions | Covered through shared voucher stack | Bank-ledger-specific live verification needed |
| Cash voucher | Ready With Conditions | Covered through shared voucher stack | Cash-control live verification needed |
| Purchase invoices and notes | Ready With Conditions | Strongest automation estate, signoff scripts, and deep route coverage | Final rerun in release environment and business signoff |
| Purchase statutory | Ready With Conditions | Docs, UAT material, and P1 coverage are strong | Live totals and classification signoff |
| Purchase settings and charge types | Ready With Conditions | Settings routes and P1 coverage exist | Live propagation into transactions |
| Purchase print and exports | Needs Live Verification | Good browser evidence exists, but print/export correctness is environment-sensitive | Manual output verification |
| Purchase legacy import | Ready With Conditions | Docs, route presence, and automation exist | Representative sample import on release env |
| Sales invoices and notes | Ready With Conditions | Very strong automation depth and downstream reconciliation evidence | Final rerun in release environment and business signoff |
| Sales compliance | Ready With Conditions | Compliance flows, dialogs, payload checks, and artifact availability are covered | Live provider/integration behavior and real posting chain check |
| Sales TCS | Ready With Conditions | Strong browser and statutory coverage exists | Final business validation on actual filing posture |
| Sales settings and charge types | Ready With Conditions | Settings coverage exists | Live propagation into transactions |
| Sales bulk print | Needs Live Verification | Route and component exist, but direct proof is lighter | Bulk output sanity check |
| Sales legacy import | Needs Live Verification | Route exists, but direct proof is comparatively thin | End-to-end import validation |
| Catalog and product masters | Ready With Conditions | Strong master footprint and P2 coverage exist | Propagation into transactions and deactivation checks |
| Inventory operations | Ready With Conditions | CRUD and report-interaction evidence exists | Live stock movement and downstream report validation |
| Inventory reporting | Ready With Conditions | Broad browser and filter coverage exists | Large-data and totals signoff |
| Manufacturing workspaces | Ready With Conditions | Real workspaces and browser coverage exist | Costing and operational lifecycle signoff |
| Manufacturing reporting and reconciliation | Needs Live Verification | Report shells and drilldowns exist but confidence is lower than commercial core | Quantitative output validation |
| Assets / fixed assets | Ready With Conditions | Real module, docs, and purchase-to-asset evidence exist | Live depreciation and ledger impact signoff |
| Bank reconciliation | Ready With Conditions | Strong route, API, docs, and P1 evidence exist | Mutation-submit, reload-persistence, and downstream report closure in live env |
| Financial hub reports | Ready With Conditions | Deep browser and parity coverage exists | Final totals and performance signoff on release dataset |
| Payables reports | Ready With Conditions | Mature browser and seeded/live evidence exists | Final totals and downstream parity signoff |
| Receivables reports | Ready With Conditions | Mature browser and reconciliation evidence exists | Final totals and downstream parity signoff |
| Compliance reports | Ready With Conditions | Strong browser, matrix, and baseline evidence exists | Filing-readiness and exception-output manual validation |
| GST reports | Ready With Conditions | Docs and report-browser coverage are strong | Final bucket-total and export signoff |
| GST reconciliation | Needs Live Verification | Dedicated module and rollout docs exist, but maturity is explicitly pilot-like | Production-scope decision and performance validation |
| GST-TDS | Needs Live Verification | Config route and some coverage exist | End-to-end output validation |
| TCS configuration and filing | Ready With Conditions | Good config and browser coverage exists | Filing lifecycle signoff |
| Withholding | Needs Live Verification | Backend presence is meaningful, but end-to-end proof is thinner | Posting/report chain validation |
| Payroll core | Ready With Conditions | Strong codebase, docs, and dedicated suite exist | Live payroll run and posting validation |
| Payroll ESS | Needs Live Verification | Frontend breadth exists, but direct release-signoff evidence is lighter | User-role and workflow verification |
| Payroll approvals and policies | Needs Live Verification | Functional surface exists, but scenario coverage is lighter | Manual approval chain signoff |
| Payroll reporting and posting | Needs Live Verification | Docs and surfaces exist | Live report and posting proof |
| HRMS | Needs Live Verification | Real module exists but direct evidence is lighter | Explicit release-scope verification |
| Commerce | Deferred or Needs Scope Decision | Module exists but does not appear as a core release-confidence area | Confirm whether included in this release |
| Retail | Deferred or Needs Scope Decision | Module exists but has light evidence | Confirm whether included in this release |
| Subscriptions | Deferred or Needs Scope Decision | More planning-oriented than proven production module | Confirm whether included in this release |
| Invoice import | Ready With Conditions | Shared import center plus backend/docs exist | Final release-env import pass |
| Inventory and manufacturing admin surfaces | Needs Live Verification | Settings browser coverage exists | Propagation and permission signoff |
| Audit logging | Needs Live Verification | Support app exists, but release-grade proof is missing | Manual audit trail verification |
| Error logging | Not Ready | Repo structure alone does not prove usable production observability | Explicit production logging validation required |
| Helpers and core support libraries | Ready With Conditions | Mature modules depend on them and current stack is broadly stable | No direct blocker seen, but regression rerun still needed |

### Immediate Release Blockers From This Audit

- observability and support-readiness are not yet proven from current evidence
- GST reconciliation should not be treated as broad-production-ready without an explicit rollout decision
- numbering, withholding, GST-TDS, and lighter payroll/HRMS surfaces still need live verification
- print/export flows need manual output validation even where browser automation exists
- deferred modules such as commerce, retail, and subscriptions need an explicit scope decision before signoff

### Best Next Execution Pass

1. Run the commercial smoke and signoff suites in the release environment.
2. Perform live posting and downstream report parity checks for vouchers, purchase, sales, and bank reconciliation.
3. Validate report totals and exports for financial, payables, receivables, GST, and compliance hubs.
4. Run payroll live verification for runs, posting preview, ESS, and approvals.
5. Complete observability, rollback, and support-runbook signoff.

## Practical Note

For production release, the highest-risk items are the places where configuration, posting, reconciliation, or report parity can silently drift even when a screen appears usable. This matrix is intentionally biased toward those release risks rather than only UI reachability.
