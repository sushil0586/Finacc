# CFO Control Layer Phased Implementation Plan

Date: 2026-09-24

Target repositories:

- Backend: `/Users/ansh/finacc-angular/finacc-django/Finacc`
- Frontend: `/Users/ansh/finacc-angular/accountproject`
- UI tests: `/Users/ansh/Documents/finacc-ui-tests`

## Objective

Build a CFO-facing control layer on top of the existing accounting, statutory, bank reconciliation, payroll, inventory, purchase, sales, and reporting modules.

The goal is not to add more isolated accounting screens. The goal is to make the system answer the questions a CFO asks every day:

- How much cash do we have?
- What will cash look like over the next 13 weeks?
- Which customers are delaying collections?
- Which vendor payments are due or risky?
- Are GST, TDS, payroll, bank reconciliation, and books-close tasks under control?
- Where are actuals deviating from budget?
- Which exceptions need approval before books can be trusted?

## Product Direction

Create these major CFO workspaces:

1. CFO Control Tower
2. Cash Flow Forecast
3. Receivables Command Center
4. Payables Control Center
5. Monthly Close Cockpit
6. Budget vs Actual
7. Approval and Exception Center
8. CFO MIS Pack

## Phase 0: Baseline And Contracts

Status: `planned`

### Goal

Map existing backend, frontend, and Playwright coverage before building new CFO screens.

### What We Will Create

- CFO data contract inventory
- Existing API-to-CFO-metric mapping
- Missing backend endpoint list
- Frontend route and menu placement plan
- Test data requirements for CFO scenarios

### Backend Work

- Identify reusable data from:
  - vouchers
  - posting
  - sales
  - purchase
  - receipts
  - payments
  - bank reconciliation
  - GST reconciliation
  - TDS/GST-TDS/TCS compliance
  - payroll
  - inventory/manufacturing
  - financial reports
- Define canonical response shapes for CFO widgets and drilldowns.
- Confirm entity, financial year, branch/subentity, and permission scoping rules.

### Frontend Work

- Decide main route structure:
  - `/cfo`
  - `/cfo/cash-flow`
  - `/cfo/receivables`
  - `/cfo/payables`
  - `/cfo/month-close`
  - `/cfo/budget-vs-actual`
  - `/cfo/approvals`
  - `/cfo/mis-pack`
- Add menu grouping under management/reporting, depending on current RBAC menu structure.

### Playwright Work

- Create CFO smoke matrix.
- Reuse existing authenticated setup.
- Define seed data assumptions for customer dues, vendor dues, bank balances, GST/TDS dues, and close tasks.

### Done When

- Every CFO dashboard metric has a named source or a documented backend gap.
- Phase 1 can start without guessing data ownership.

## Phase 1: CFO Control Tower

Status: `planned`

### Goal

Create the first CFO landing dashboard with actionable finance health cards and exception queues.

### What We Will Implement

Backend endpoint:

- `GET /api/cfo/control-tower/summary/`

Frontend page:

- `/cfo`

Core cards:

- Cash and bank balance
- Receivables overdue
- Payables due
- GST/TDS statutory payable
- Current month revenue and expense
- Gross margin / net margin snapshot
- Bank reconciliation pending count
- Month-close progress
- Approval pending count

Drilldown sections:

- Critical receivables
- Critical vendor payments
- Compliance due soon
- Reconciliation exceptions
- Approval exceptions

### Backend Work

- Add a new `cfo` Django app or a clearly separated `dashboard/services/cfo_*` service layer.
- Implement aggregate service functions:
  - cash position
  - receivable aging summary
  - payable aging summary
  - compliance liability summary
  - reconciliation exception summary
  - approval queue summary
  - month-close status summary
- Apply entity/financial-year/subentity scope consistently.
- Add response serializer with explicit decimal/date fields.

### Frontend Work

- Create CFO dashboard module/page.
- Add compact finance cards with status colors.
- Add exception tables with direct navigation to source modules.
- Add filters:
  - entity
  - financial year
  - period
  - branch/subentity if enabled

### Playwright Work

- CFO dashboard loads under an authorized user.
- Cards render stable numeric values.
- Drilldown rows open correct source routes.
- Empty state renders cleanly for a new entity.
- Permission-gated user cannot access CFO dashboard.

### Done When

- CFO can open one page and see finance health without visiting 8 different modules.

## Phase 2: Receivables And Payables Control

Status: `planned`

### Goal

Give CFOs collection and payment control, not only aging reports.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/receivables/aging/`
- `GET /api/cfo/receivables/worklist/`
- `PATCH /api/cfo/receivables/follow-up/<id>/`
- `GET /api/cfo/payables/aging/`
- `GET /api/cfo/payables/worklist/`
- `PATCH /api/cfo/payables/payment-priority/<id>/`

Frontend pages:

- `/cfo/receivables`
- `/cfo/payables`

Receivables features:

- Customer aging buckets: current, 0-30, 31-60, 61-90, 90+
- Invoice-wise outstanding
- Follow-up owner
- Promise-to-pay date
- Collection risk status
- Customer credit exposure

Payables features:

- Vendor aging buckets
- Due this week / overdue / blocked
- Payment priority
- GST/TDS compliance flags
- Duplicate invoice warning surface
- Suggested payment run list

### Backend Work

- Reuse sales invoice, receipt, purchase invoice, payment, and ledger data.
- Add follow-up/status models only if current models do not support action tracking.
- Add aging calculation services with date-cutoff consistency.
- Add export-ready response rows.

### Frontend Work

- Build two operational grids optimized for scanning and action.
- Add filters:
  - customer/vendor
  - aging bucket
  - owner
  - risk/status
  - due date range
- Add inline action controls for follow-up status and payment priority.

### Playwright Work

- Aging bucket totals match row totals.
- Promise-to-pay update persists after reload.
- Vendor priority update persists after reload.
- Filters and export rows remain consistent.
- Drilldown to source invoice/vendor/customer works.

### Done When

- CFO can run collections and vendor payment review from dedicated worklists.

## Phase 3: 13-Week Cash Flow Forecast

Status: `planned`

### Goal

Predict weekly cash position from bank balance, collections, vendor payments, payroll, taxes, and manual CFO adjustments.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/cash-flow/forecast/`
- `POST /api/cfo/cash-flow/adjustments/`
- `PATCH /api/cfo/cash-flow/adjustments/<id>/`
- `DELETE /api/cfo/cash-flow/adjustments/<id>/`

Frontend page:

- `/cfo/cash-flow`

Forecast lines:

- Opening cash
- Expected customer receipts
- Expected vendor payments
- Payroll outflow
- GST/TDS/statutory outflow
- Loan/interest/recurring payments if available
- Manual inflow/outflow adjustments
- Net movement
- Closing projected cash

### Backend Work

- Build weekly bucket generator for 13 weeks.
- Pull source schedules from receivables, payables, payroll, statutory liabilities, and payments.
- Add `CashFlowForecastAdjustment` model for CFO-entered assumptions.
- Track adjustment audit metadata.
- Support conservative/base/optimistic scenario labels if lightweight enough for Phase 3.

### Frontend Work

- Build weekly forecast grid.
- Show shortfall weeks clearly.
- Allow CFO manual adjustments with reason.
- Add scenario selector if backend supports it.
- Add source drilldowns for forecast components.

### Playwright Work

- 13 weekly buckets render.
- Manual adjustment changes the projected balance.
- Deleted adjustment reverses impact.
- Negative projected cash is highlighted.
- Source drilldown opens receivable/payable/payroll/statutory detail.

### Done When

- CFO can see expected cash pressure before it becomes a bank balance problem.

## Phase 4: Monthly Close Cockpit

Status: `planned`

### Goal

Make month-end closing visible, controlled, and auditable.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/month-close/status/`
- `POST /api/cfo/month-close/tasks/<task_code>/mark-complete/`
- `POST /api/cfo/month-close/tasks/<task_code>/reopen/`
- `POST /api/cfo/month-close/lock-period/`
- `POST /api/cfo/month-close/unlock-period/`

Frontend page:

- `/cfo/month-close`

Close checklist:

- Bank reconciliation completed
- GST reconciliation completed
- TDS/TCS reviewed
- Payroll posted
- Inventory valuation completed
- Depreciation posted
- Accruals/provisions posted
- Trial balance reviewed
- Financial reports reviewed
- Period locked

### Backend Work

- Add close-period and close-task models if not already available.
- Auto-evaluate tasks where possible from existing module states.
- Require reason for manual completion/reopen.
- Add period lock enforcement integration plan with vouchers/posting.

### Frontend Work

- Build task cockpit with status, owner, due date, evidence link, and blocker reason.
- Add complete/reopen controls with confirmation.
- Add period lock CTA with strong warning.

### Playwright Work

- Task status renders from backend.
- Complete/reopen actions persist.
- Locked period blocks restricted edits where enforcement exists.
- Evidence links navigate to source modules.

### Done When

- CFO can know whether books are actually close-ready.

## Phase 5: Budget Vs Actual

Status: `planned`

### Goal

Give CFOs variance visibility by account, department, cost center, branch, and month.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/budgets/`
- `POST /api/cfo/budgets/import/`
- `GET /api/cfo/budget-vs-actual/`
- `GET /api/cfo/budget-vs-actual/drilldown/`

Frontend page:

- `/cfo/budget-vs-actual`

Features:

- Budget upload/import
- Monthly budget grid
- Actuals from posted ledger
- Variance amount and percentage
- Drilldown to vouchers
- CFO remarks per variance line

### Backend Work

- Add budget header/line models.
- Support dimensions:
  - account
  - month
  - entity
  - financial year
  - branch/subentity if applicable
  - department/cost center if available
- Create actuals aggregation from posted ledger.
- Add variance comment model or metadata.

### Frontend Work

- Build budget import and review screen.
- Build variance analysis grid.
- Add drilldown drawer/table for source vouchers.
- Add comments/status per variance.

### Playwright Work

- Budget import creates lines.
- Actual posting changes variance.
- Drilldown total matches variance actual.
- CFO comment persists after reload.

### Done When

- CFO can explain why actuals differ from plan with voucher-level support.

## Phase 6: Approval And Exception Center

Status: `planned`

### Goal

Centralize high-risk finance approvals and exception handling.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/approvals/queue/`
- `POST /api/cfo/approvals/<id>/approve/`
- `POST /api/cfo/approvals/<id>/reject/`
- `POST /api/cfo/approvals/<id>/request-info/`

Frontend page:

- `/cfo/approvals`

Approval categories:

- High-value vouchers
- Backdated entries
- Payment runs
- Vendor payment exceptions
- Credit limit override
- Period unlock requests
- Bank reconciliation exception closure
- Budget override

### Backend Work

- Audit current approval/maker-checker support.
- Define unified approval queue service even if source modules store approvals differently.
- Add reason/comment requirement.
- Preserve source object traceability.

### Frontend Work

- Build approval queue with filters and source drilldown.
- Add approve/reject/request-info actions.
- Add impact preview for high-risk approvals.

### Playwright Work

- Pending approvals render by category.
- Approve/reject action updates status.
- Unauthorized user cannot approve.
- Source drilldown works.

### Done When

- CFO has one queue for financial risk decisions.

## Phase 7: CFO MIS Pack

Status: `planned`

### Goal

Generate a monthly board/management pack from trusted finance data.

### What We Will Implement

Backend endpoints:

- `GET /api/cfo/mis-pack/preview/`
- `POST /api/cfo/mis-pack/generate/`
- `GET /api/cfo/mis-pack/history/`

Frontend page:

- `/cfo/mis-pack`

Pack sections:

- P&L summary
- Balance sheet summary
- Cash flow summary
- Working capital
- Receivables aging
- Payables aging
- Tax/compliance status
- Inventory/manufacturing summary where applicable
- Payroll cost summary
- Exceptions and open risks

### Backend Work

- Create MIS pack assembly service.
- Reuse financial report services where possible.
- Store generated pack metadata.
- Support Excel first; PDF can follow after layout stabilizes.

### Frontend Work

- Build preview screen.
- Allow section selection.
- Show generated pack history.
- Add download action.

### Playwright Work

- Preview renders selected period.
- Generate creates history entry.
- Download endpoint responds successfully.
- Pack totals match source report totals for sampled sections.

### Done When

- CFO can produce a repeatable monthly management pack without manual spreadsheet assembly.

## Cross-Cutting Requirements

### RBAC And Permissions

Create or map permissions:

- `cfo.control_tower.view`
- `cfo.receivables.view`
- `cfo.receivables.manage_followup`
- `cfo.payables.view`
- `cfo.payables.manage_priority`
- `cfo.cash_flow.view`
- `cfo.cash_flow.manage_adjustments`
- `cfo.month_close.view`
- `cfo.month_close.manage`
- `cfo.month_close.lock_period`
- `cfo.budget.view`
- `cfo.budget.manage`
- `cfo.approvals.view`
- `cfo.approvals.action`
- `cfo.mis_pack.view`
- `cfo.mis_pack.generate`

### Audit

Every CFO action must write an audit trail:

- adjustment created/edited/deleted
- follow-up changed
- payment priority changed
- close task completed/reopened
- period locked/unlocked
- budget imported
- variance comment changed
- approval approved/rejected/requested-info
- MIS pack generated

### Data Integrity

All aggregate totals must be drillable or explainable:

- summary card total should reconcile to worklist rows
- worklist rows should reconcile to source invoices/vouchers
- forecast lines should show source category
- budget actuals should reconcile to posted ledger

### UX Standards

- CFO pages should be dense, quiet, and operational.
- Avoid marketing-style hero sections.
- Use compact cards, grids, filters, tabs, and drilldown drawers.
- Use direct source links wherever the CFO needs evidence.
- Empty states must be useful for fresh entities.

## Recommended Build Order

1. Phase 0: Baseline and contracts
2. Phase 1: CFO Control Tower
3. Phase 2: Receivables and Payables Control
4. Phase 3: 13-week Cash Flow Forecast
5. Phase 4: Monthly Close Cockpit
6. Phase 5: Budget vs Actual
7. Phase 6: Approval and Exception Center
8. Phase 7: CFO MIS Pack

## First Implementation Slice

The first code slice should be intentionally small but production-shaped:

### Backend

- Create CFO service layer.
- Add `GET /api/cfo/control-tower/summary/`.
- Return:
  - cash summary
  - receivables summary
  - payables summary
  - compliance summary
  - bank reconciliation summary
  - close readiness placeholder
  - approvals placeholder

### Frontend

- Create `/cfo` route.
- Add CFO dashboard shell.
- Render the summary cards.
- Add exception/worklist preview sections.
- Add navigation placeholders to future CFO pages.

### UI Tests

- Add CFO dashboard smoke spec.
- Verify authorized load.
- Verify core cards render.
- Verify empty state does not break.
- Verify unauthorized user is blocked.

## Delivery Milestones

### Milestone 1

CFO Control Tower visible and backed by real aggregates.

### Milestone 2

Receivables and payables worklists drive collections and payment review.

### Milestone 3

Cash forecast predicts 13-week closing balance with CFO adjustments.

### Milestone 4

Month-close cockpit controls close readiness and period lock.

### Milestone 5

Budget vs actual gives variance drilldown.

### Milestone 6

Approval center centralizes CFO decisions.

### Milestone 7

MIS pack generates repeatable management reporting.

