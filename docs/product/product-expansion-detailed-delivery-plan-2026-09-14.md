# Product Expansion Detailed Delivery Plan

Status: Planning baseline

Last updated: 14 September 2026

Parent roadmap: [Product Expansion Priority Roadmap](product-expansion-priority-roadmap-2026-09-14.md)

Active execution plans:

- [P0 Pilot And Launch Hardening Plan](../qa/p0-pilot-launch-hardening-plan-2026-09-14.md)
- [P0 Core Launch Scope And Traceability Register](../qa/p0-core-launch-scope-traceability-register-2026-09-14.md)
- [P1 HRMS And Payroll Launch Readiness Plan](../payroll/p1-hrms-payroll-launch-readiness-plan-2026-09-14.md)
- [P1 HRMS And Payroll Phase 0 Scope Register](../payroll/p1-hrms-payroll-phase0-scope-traceability-register-2026-09-14.md)

Portfolio rule: P2-P10 implementation is frozen until P0 and P1 have both passed their launch gates.

## Purpose

This document translates the product roadmap into implementable and certifiable workstreams. Each phase must update its status, evidence, unresolved risks, and next decision in this document or a linked workstream plan.

## Common Delivery Model

Every workstream follows the same delivery lifecycle:

| Phase | Deliverable | Required evidence |
| --- | --- | --- |
| 0. Discovery | Personas, workflows, accounting rules, compliance rules, non-goals, and success measures | Approved charter and traceability matrix |
| 1. Domain foundation | Models, effective dates, state machine, numbering, permissions, migrations, and audit events | Model/service tests and migration rehearsal |
| 2. Core operations | APIs and transactional services with idempotency and concurrency controls | API lifecycle and negative tests |
| 3. User experience | Complete desktop/mobile workflows, guidance, validation, empty/loading/error states | Angular tests and UX review |
| 4. Accounting and reports | Posting, reversal, settlement/allocation, statutory and management reports | Source-to-GL-to-report reconciliation |
| 5. Integration and recovery | Imports, exports, external providers, retries, rollback, and diagnostics | Failure-injection and recovery evidence |
| 6. Certification | RBAC, isolation, accessibility, browsers, performance, repeated staging runs | Signed launch matrix and runbook |

## P0: Pilot And Launch Hardening

### Objective

Turn the current implementation into a controlled, supportable release baseline before product breadth increases.

### Scope

- Complete unresolved evidence in existing sales, purchase, financial-report, inventory/manufacturing, assets, HRMS, payroll, compliance, and platform-operation plans.
- Establish a single module-by-role-by-screen coverage register.
- Certify backup restore, migration rollback, incident diagnostics, audit retention, alerting, and external-provider degradation.
- Run production-like concurrency and volume tests for posting, imports, reports, payroll, inventory movement, and document generation.
- Approve desktop/mobile screenshots and accessibility checks for critical workflows.

### Exit Gate

- No open severity-1 or severity-2 defect affecting accounting, security, data loss, compliance, or tenant isolation.
- Three consecutive clean staging runs of the launch suite.
- Recovery-point and recovery-time objectives demonstrated.
- Pilot support owner, escalation path, dashboards, and rollback runbook approved.

## P1: HRMS And Payroll Completion

### Objective

Allow an implementation operator to onboard a customer and run the complete employee-to-payroll-to-accounting lifecycle without hidden setup or placeholder screens.

### Functional Scope

- Guided organization, location, department, designation, shift, holiday, leave, and attendance setup.
- Employee onboarding, documents, contracts, bank details, statutory identity, and employment lifecycle.
- Effective-dated salary structures, component formulas, eligibility, arrears, revisions, bonuses, loans, reimbursements, and deductions.
- Attendance-to-payroll inputs, payroll preview, exception correction, approval, lock, posting, payment export, payslip, reversal, and rerun.
- PF, ESI, professional tax, labour welfare, income tax declarations/evidence, and statutory outputs where applicable.
- Employee self-service for profile, attendance, leave, claims, declarations, payslips, loans, and final settlement status.
- Administrator workbench for full-and-final settlement and governed bank-file generation.

### Accounting Scope

- Entity-facing effective-dated payroll ledger policies and component posting mappings.
- Department, branch, project, and cost-centre dimensions.
- Gross-to-net reconciliation, employer liabilities, payable clearing, payment, reversal, and prior-period adjustment.
- Payroll register, liability schedules, employee ledger, bank advice, statutory reports, and GL agreement.

### Delivery Phases

1. Convert the existing HRMS/payroll backlog into a screen/API/accounting traceability register.
2. Complete guided onboarding and configuration readiness checks.
3. Complete payroll inputs, calculation, exception handling, approval, and lock.
4. Complete posting, payment, statutory outputs, reimbursement, and final settlement.
5. Complete employee/admin self-service and operational reports.
6. Certify roles, scope, recovery, volume, browser, mobile, and accessibility behavior.

### Exit Gate

A newly onboarded customer can run two consecutive payroll periods, post and pay them, reverse a controlled error, and reconcile payroll registers, liabilities, bank output, and GL to zero unexplained difference.

## P2: Banking, Treasury, And Cash Operations

### Objective

Connect book balances to real bank activity and govern outgoing and incoming cash operations.

### Functional Scope

- Bank account master, signatories, limits, payment methods, and approval policies.
- Statement import formats and optional bank-feed/provider adapters.
- Rule-assisted reconciliation, split matching, one-to-many/many-to-one matching, fees, interest, and unresolved queues.
- Payment proposals and batches for vendors, payroll, taxes, refunds, and inter-account transfers.
- Cheque lifecycle, payment-file generation, status acknowledgement, rejection, retry, and cancellation.
- Cash position, short-term forecast, facility/loan register, maturity calendar, and treasury dashboard.

### Accounting Scope

- Bank, clearing, undeposited funds, fees, interest, FX, and transfer postings.
- Payment allocation to AP/AR/payroll/tax liabilities.
- Reconciliation audit trail preserving statement line, book entry, matcher, and approval evidence.

### Exit Gate

A statement period can be imported, matched, adjusted, approved, and closed with the bank reconciliation, cashbook, ledger, and GL agreeing exactly; retries cannot duplicate payments or postings.

## P3: Procurement And Three-Way Matching

### Objective

Extend purchase-to-pay upstream from demand and sourcing through controlled receipt and invoice acceptance.

### Functional Scope

- Purchase requisitions, budgets, approvals, RFQs, vendor quotations, and comparison.
- Purchase orders, contracts, blanket orders, releases, amendments, and closures.
- Goods/service receipts, inspection, rejection, returns, short/excess receipt, and landed cost.
- Two-way/three-way matching with tolerance policies and exception workbench.
- Vendor performance, lead-time, quality, price variance, and contract utilization.

### Accounting Scope

- Commitments and budget consumption.
- GRNI/receipt accrual, inventory or expense recognition, landed-cost allocation, invoice clearing, AP, and payment.
- Price, quantity, exchange, and purchase variances with reversal behavior.

### Exit Gate

PO, receipt, invoice, credit/debit note, payment, inventory, AP aging, purchase register, and GL reconcile for partial, over/under, rejected, returned, and foreign-currency scenarios.

## P4: Order-To-Cash And Collections

### Objective

Extend sales downstream and upstream so commercial commitments, fulfilment, billing, credit, and collection form one traceable lifecycle.

### Functional Scope

- Leads or customer requests where needed, quotations, approvals, sales orders, pricing, discounts, and contracts.
- Availability, reservation, allocation, picking, dispatch, delivery challans, proof of delivery, returns, and cancellations.
- Milestone, recurring, usage, advance, and consolidated billing patterns.
- Credit limits, holds, exception approvals, collection worklists, promises to pay, disputes, dunning, and write-offs.
- Customer statements and self-service invoice/payment access.

### Accounting Scope

- Customer advances, revenue, taxes, inventory/COGS, receivables, receipts, allocation, refund, bad debt, and reversal.
- Order margin, fulfilment, AR aging, collection effectiveness, and cash application reporting.

### Exit Gate

Quote/order, fulfilment, invoice/note, stock, revenue/COGS, receivable, receipt/allocation, GST, and financial reports agree across partial and exceptional flows.

## P5: Advanced Indian Statutory Compliance

### Objective

Move from transaction-level tax support to a governed compliance operations product.

### Functional Scope

- GST registration profiles, place-of-supply, HSN/SAC, rate, exemption, RCM, ITC eligibility, and effective-dated policy governance.
- GSTR-1, GSTR-3B, IMS/2B reconciliation, amendment, debit/credit note, advance, export/SEZ, and filing-period controls.
- E-invoice and e-way bill generation, cancellation, extension, status polling, provider outage, retry, and evidence.
- TDS/TCS setup, deduction/collection, deposit, return preparation, certificates, correction, and reconciliation.
- Compliance calendar, notices, tasks, ownership, documents, filing status, and audit pack.

### Integration Scope

- Provider abstraction around WhiteBooks and future providers.
- Secret isolation, environment controls, idempotency keys, request/response redaction, rate limits, and provider observability.

### Exit Gate

Source documents, statutory registers, return summaries, provider acknowledgements, tax ledgers, payments, and GL reconcile for normal, amended, cancelled, retried, and prior-period scenarios.

## P6: Warehouse And Advanced Manufacturing

### Objective

Support physical stock control and production planning at operational scale while preserving valuation integrity.

### Functional Scope

- Warehouses, zones, bins, put-away, picking, packing, reservation, replenishment, barcode/QR, serial/batch, expiry, and cycle count.
- MRP, demand/supply planning, BOM versions, routings, work centres, capacity, production orders, issues, completions, scrap, rework, by-products, and subcontracting.
- Quality plans, inspection, quarantine, release, rejection, and traceability.
- Standard, moving-average, FIFO or supported valuation policies with governed effective dates.

### Accounting Scope

- Inventory, GRNI, WIP, consumption, absorption, overhead, output, scrap, subcontracting, and production variances.
- Stock ledger, valuation, material summary, production variance, trading account, P&L, balance sheet, and GL reconciliation.

### Exit Gate

Physical quantity, reservations, batch/serial genealogy, valuation layers, production consumption/output, variances, stock reports, and GL agree under concurrency and backdated/reversal scenarios.

## P7: Budgeting, Forecasting, And Project Accounting

### Objective

Add forward-looking control and project profitability over reliable actuals.

### Functional Scope

- Versioned budgets by account, branch, department, project, and period.
- Approval, transfer, supplement, commitment, warning/block controls, and variance commentary.
- Rolling P&L, balance sheet, cash-flow, sales, purchase, payroll, and inventory forecasts.
- Projects, tasks, contracts, milestones, timesheets, expenses, procurement, billing, WIP, revenue recognition, and profitability.

### Exit Gate

Budget, commitment, actual, forecast, project cost, billing, WIP/revenue recognition, cash projection, and GL are traceable and reconcilable by dimension.

## P8: Multi-Company Consolidation And Group Finance

### Objective

Support organizations operating several legal entities while preserving separate books and producing governed group results.

### Functional Scope

- Group hierarchy, ownership, reporting calendars, chart mappings, currencies, and consolidation versions.
- Intercompany billing, balances, matching, settlement, loans, allocations, and eliminations.
- Currency translation, minority interest, acquisition/disposal changes, adjustments, close checklist, and consolidated reporting.

### Exit Gate

Entity trial balances map to consolidation, intercompany differences are resolved or disclosed, eliminations balance, currency translation is repeatable, and consolidated statements drill back to source entries.

## P9: Portals, Workflow, And Document Intelligence

### Objective

Reduce manual coordination while keeping domain services as the system of record.

### Functional Scope

- Vendor portal for onboarding, quotations, invoices, status, disputes, and statements.
- Customer portal for orders, invoices, payments, statements, and support.
- Employee portal for HRMS/payroll self-service.
- Configurable approvals, conditions, escalations, delegation, notifications, SLA timers, and webhooks.
- OCR-assisted capture, document classification, evidence linking, retention, search, versioning, and electronic-signature integration.

### Exit Gate

External users can complete scoped workflows without gaining tenant or financial access, and automation failures are visible, retryable, auditable, and idempotent.

## P10: Specialized Product Verticals

### Candidate Modules

- CRM and service management.
- Retail/POS and store operations.
- Subscription billing, dunning, and revenue recognition.
- Construction and contract accounting.
- Professional-services automation.
- Distribution, healthcare, education, hospitality, and nonprofit packs.

### Entry Rule

No candidate enters implementation until customer discovery identifies its buyer, frequency, revenue opportunity, regulatory needs, overlap with core modules, support burden, and minimum viable end-to-end workflow.

### Architecture Rule

Industry behavior must be expressed through configuration, extension points, and domain services. It must not fork core posting, tax, permissions, or reporting logic.

## Cross-Workstream Architecture

The following shared capabilities should be extended incrementally as verticals require them:

- Effective-dated policy and configuration engine.
- Document lifecycle and approval state machine.
- Idempotency, optimistic concurrency, locking, and reversal services.
- Posting contracts, subledger reconciliation, and source drilldown.
- Dimension framework for branch, department, location, project, cost centre, and channel.
- File import/export, background jobs, retry, and manifest services.
- Notification, task, SLA, and webhook services.
- Provider adapter, secret, environment, telemetry, and redaction controls.
- Report/export framework with common scope, pagination, totals, and evidence metadata.

## Testing And Certification Matrix

Every vertical must cover:

| Quality area | Minimum gate |
| --- | --- |
| Correctness | Unit, service, serializer/API, calculation, state transition, and migration tests |
| Accounting | Balanced postings, reversal, settlement, subledger/GL/report reconciliation, rounding, and period controls |
| Compliance | Effective-dated rules, required evidence, statutory totals, amendments, and audit history |
| Security | Role/action matrix, object-level permission, entity/branch/FY isolation, export and attachment controls |
| Reliability | Duplicate submit, timeout, retry, partial failure, rollback, concurrency, offline/interruption, and provider outage |
| UX | Every field, action, validation, empty/loading/error/success state, keyboard path, mobile layout, and user guidance |
| Accessibility | Automated scans plus manual focus order, labels, names, contrast, dialogs, and screen-reader critical path |
| Compatibility | Chromium, Firefox, WebKit, desktop, tablet, and supported mobile widths |
| Performance | Defined budgets for list, search, save, post, report, import/export, and representative batch/concurrency |
| Operations | Metrics, logs, audit trail, alert, runbook, backup/restore, migration and rollback rehearsal |

## Evidence And Status Template

Create or update one row after each phase:

| Workstream | Phase | Status | Backend evidence | Frontend evidence | Browser/staging evidence | Open risks | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Example | Phase 0 | Not started | - | - | - | - | Hold |

Allowed statuses: `Not started`, `In progress`, `Blocked`, `Passed`, `Passed with residual risk`, `Superseded`.

## Initial Execution Backlog

1. Execute P0 Phase 0 and complete the cross-module launch matrix using existing sign-off documents.
2. Execute P1 Phase 0 and convert the HRMS/payroll backlog into a screen, API, posting, report, role, and test inventory.
3. Draft banking/treasury and procurement discovery charters without beginning P2/P3 implementation.
4. Identify shared approval, effective-date, payment, reconciliation, and provider components before duplicating them.
5. Establish release dashboards for defect severity, automated coverage, flaky tests, reconciliation differences, and performance budgets.

## Phase Update Log

| Date | Workstream | Update | Result | Next action |
| --- | --- | --- | --- | --- |
| 14 September 2026 | Portfolio | Created detailed plan for P0-P10 and common certification gates. | Planning baseline established. | Build P0 launch matrix, then start P1 discovery inventory. |
