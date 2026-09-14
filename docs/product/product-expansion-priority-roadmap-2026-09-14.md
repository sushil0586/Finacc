# Product Expansion Priority Roadmap

Status: Approved planning baseline

Last updated: 14 September 2026

Detailed delivery plan: [Product Expansion Detailed Delivery Plan](product-expansion-detailed-delivery-plan-2026-09-14.md)

Active launch plans:

- [P0 Pilot And Launch Hardening Plan](../qa/p0-pilot-launch-hardening-plan-2026-09-14.md)
- [P1 HRMS And Payroll Launch Readiness Plan](../payroll/p1-hrms-payroll-launch-readiness-plan-2026-09-14.md)

## Purpose

This roadmap orders Finacc product development by customer value, accounting dependency, launch risk, and reuse of the existing platform. It distinguishes three kinds of work:

- `Certify`: prove that an implemented capability is safe to launch.
- `Complete`: finish an existing vertical whose end-to-end workflow still has gaps.
- `Expand`: introduce a new product vertical after its dependencies are stable.

The roadmap does not treat a screen or API as a finished feature. A feature is complete only when its business lifecycle, accounting impact, permissions, reports, recovery behavior, and browser workflow are certified together.

## Priority Principles

1. Protect accounting integrity and the controlled pilot before adding breadth.
2. Complete workflows adjacent to the existing finance, sales, purchase, inventory, and payroll foundations.
3. Deliver a usable vertical slice before starting another large vertical.
4. Make policy, mappings, approvals, numbering, and effective dates configurable by entity.
5. Keep tenant, entity, branch, financial-year, and role isolation mandatory at every layer.
6. Require measurable release evidence instead of confidence based only on code coverage.

## Executive Roadmap

| Priority | Workstream | Type | Business outcome | Primary dependencies | Release position |
| --- | --- | --- | --- | --- | --- |
| P0 | Pilot and launch hardening | Certify | Existing ERP workflows can be operated, recovered, monitored, and supported safely | Current finance and operations modules | Required before unrestricted launch |
| P1 | HRMS and payroll completion | Complete | A customer can be onboarded from organization setup through payroll, payment, statutory reporting, and GL | Finance, banking exports, RBAC | First product-completion wave |
| P2 | Banking, treasury, and cash operations | Expand | Bank transactions, reconciliation, payment execution, cash visibility, and controls work end to end | GL, AP, AR, approvals | Enables scalable finance operations |
| P3 | Procurement and three-way matching | Expand | Requisition-to-payment is controlled from demand through PO, receipt, invoice, and payment | Purchase, inventory, AP, banking | Completes purchase-to-pay upstream |
| P4 | Order-to-cash and collections | Expand | Quote/order-to-dispatch, billing, credit control, collection, and settlement are integrated | Sales, inventory, AR, banking | Completes commercial sales lifecycle |
| P5 | Advanced Indian statutory compliance | Complete/Expand | GST, TDS, TCS, e-invoice, e-way bill, notices, amendments, and filing evidence are governed | Sales, purchase, withholding, WhiteBooks | Compliance differentiation wave |
| P6 | Warehouse and advanced manufacturing | Expand | Bin, batch, serial, reservation, MRP, routing, production, quality, and costing are controlled | Inventory valuation, procurement, sales orders | Operational scale wave |
| P7 | Budgeting, forecasting, and project accounting | Expand | Management can plan, control spend, measure projects, and forecast cash and profit | Stable GL dimensions and operational actuals | Management-control wave |
| P8 | Multi-company consolidation and group finance | Expand | Groups can process intercompany activity and produce consolidated statements | Mature close, FX, reporting, entity isolation | Mid-market/enterprise wave |
| P9 | Self-service portals, workflow builder, and document intelligence | Expand | Customers, vendors, employees, and operators collaborate without manual back-office relay | Mature domain workflows and notification platform | Experience and automation wave |
| P10 | CRM, service, retail, subscription, and industry packs | Expand | Finacc supports specialized revenue and operating models | Stable core platform and extension contracts | Select by validated market demand |

## Recommended Delivery Sequence

### Wave A: Launch Protection

Deliver `P0` first. Close unresolved certification in financial reporting, inventory/manufacturing, permissions, recovery, accessibility, cross-browser behavior, scale, backup restoration, and production observability.

Exit condition: controlled pilot approval with no unresolved severity-1 or severity-2 accounting, security, data-loss, or tenant-isolation defect.

### Wave B: Complete Daily Operations

Deliver `P1` to launch readiness. Banking/treasury discovery may run in parallel, but `P2` implementation remains frozen until both P0 and P1 have signed launch decisions.

Exit condition: a new customer can configure employees, run payroll, post payroll, execute or export payments, reconcile the bank, and reproduce all balances from reports.

### Mandatory P0/P1 Gate

No P2-P10 implementation may begin until:

- P0 is signed at least `Pilot Ready` with no unresolved S1/S2 defect in supported core scope.
- P1 is signed `Launch Ready` for its declared customer profile.
- Both plans have completed accounting, security, recovery, browser/mobile/accessibility, performance, observability, and support gates.
- Residual risks and unsupported behavior have named owners and visible product controls.

Discovery and architecture work may continue, but it must not create production schema, API, or UI commitments before this gate.

### Wave C: Complete Commercial Cycles

Deliver `P3`, `P4`, and `P5`. Procurement and order management must reuse common approval, document-state, allocation, tax, posting, and audit services.

Exit condition: purchase-to-pay and order-to-cash operate from source request/order through settlement and statutory reporting without offline control spreadsheets.

### Wave D: Operational Scale

Deliver `P6`, followed by `P7`.

Exit condition: stock, production, costing, budgets, and project results reconcile with the GL under representative volume and concurrency.

### Wave E: Enterprise and Ecosystem

Deliver `P8` and `P9`. Select `P10` verticals only after customer discovery establishes demand and a commercial owner.

Exit condition: group reporting and external collaboration preserve isolation, auditability, and supportability.

## Priority Decision Gates

A workstream may enter implementation only when:

- Product scope and non-goals are signed off.
- Accounting events and report effects are documented.
- Required masters, dimensions, and effective-date rules are agreed.
- Permission and isolation matrix is defined.
- Migration and backward-compatibility approach is approved.
- Backend, frontend, and browser acceptance scenarios exist.
- Operational ownership, telemetry, and recovery expectations are named.

A workstream may exit only when:

- Lifecycle actions are idempotent and concurrency protected.
- Posting and reversal balance and are traceable to the source document.
- Operational, statutory, and financial reports reconcile.
- Role, entity, branch, and financial-year isolation pass negative tests.
- Failure, retry, rollback, and duplicate-submission tests pass.
- Desktop, mobile, cross-browser, keyboard, and accessibility gates pass.
- Performance budgets and three clean repeated staging runs pass.
- Runbooks, release notes, known risks, and support diagnostics are complete.

## Portfolio Rules

- Keep one major vertical in active implementation and at most one in discovery.
- Reserve capacity in every wave for defects, migrations, observability, and test reliability.
- Do not start an industry pack by forking core accounting behavior.
- Build reusable platform services only when at least two verticals need the same capability.
- Reassess priorities after every pilot cohort using defect severity, support effort, adoption, and revenue evidence.

## Current Baseline

The existing finance, sales, purchase, withholding, assets, inventory/manufacturing, platform operations, and capital-distribution foundations provide substantial reuse. Their implementation depth is not uniform. Existing certification documents remain the authority for their verified and pending scope, including:

- [Purchase-To-Pay Production Sign-Off Plan](../qa/purchase-to-pay-production-signoff-plan-2026-09-09.md)
- [Inventory And Manufacturing Production Sign-Off Plan](../qa/inventory-manufacturing-production-signoff-plan-2026-09-08.md)
- [Organization And Capital Distribution Plan](../qa/organization-capital-distribution-development-certification-plan-2026-09-10.md)
- [HRMS And Payroll Product Backlog](../payroll/hrms-payroll-product-backlog.md)
- [Platform Operations Implementation Plan](../platform-operations-implementation-plan.md)
- [Subscription Plan Matrix](../../../docs/subscription-plan-matrix-2026-07-30.md)

## Roadmap Status Register

| Workstream | Status | Owner | Last evidence | Decision |
| --- | --- | --- | --- | --- |
| P0 Pilot and launch hardening | In progress | TBD | Phase 0 inventory register, dedicated launch plan, and module sign-off plans | Approve scope, owners, dependencies, and pilot profile |
| P1 HRMS and payroll completion | In progress | TBD | Phase 0 scope register, dedicated launch plan, and HRMS/payroll backlog | Approve first-customer profile, then begin guided-readiness work |
| P2 Banking and treasury | Discovery pending | TBD | Bank reconciliation foundation exists | Hold for charter |
| P3 Procurement | Discovery pending | TBD | Purchase-to-pay downstream exists | Hold for charter |
| P4 Order-to-cash | Discovery pending | TBD | Sales and receivables foundation exists | Hold for charter |
| P5 Advanced compliance | Discovery pending | TBD | GST/TDS/TCS foundations exist | Hold for charter |
| P6 Warehouse/manufacturing | Partial foundation | TBD | Inventory/manufacturing sign-off plan | Finish certification before expansion |
| P7 Planning/projects | Not started | TBD | None | Backlog |
| P8 Consolidation | Not started | TBD | Entity and financial-report foundations exist | Backlog |
| P9 Portals/automation | Partial foundations | TBD | Platform operations and employee views exist | Backlog |
| P10 Specialized verticals | Not started | TBD | Retail sale and subscription foundations vary | Validate demand |

## Change Log

| Date | Change |
| --- | --- |
| 14 September 2026 | Created the initial priority-ordered product expansion roadmap and linked detailed delivery plan. |
| 14 September 2026 | Added dedicated P0/P1 launch plans and froze P2-P10 implementation until both launch gates pass. |
| 14 September 2026 | Completed P0/P1 machine inventory baselines and added scope/traceability registers; formal approvals remain open. |
