# Accounting-First Product Completion Plan

Status: Phase 0 in progress

Last updated: 14 September 2026

Parent roadmap: [Product Expansion Priority Roadmap](product-expansion-priority-roadmap-2026-09-14.md)

Launch gate: [P0 Pilot And Launch Hardening Plan](../qa/p0-pilot-launch-hardening-plan-2026-09-14.md)

Phase 0 register: [Accounting Truth Matrix](../qa/accounting-truth-matrix-2026-09-14.md)

## 1. Objective

Complete and certify the accounting foundation before expanding daily operations into banking, compliance, procurement, and order-to-cash. Each phase must deliver a usable business slice whose source documents, lifecycle states, journals, subledgers, statutory effects, and reports reconcile without unexplained differences.

Remaining HRMS/payroll enhancements are paused. The currently supported payroll scope remains available, but reimbursements, expanded ESS, attendance/leave integration, bank-specific payment formats, and the full-and-final workbench stay in the payroll backlog until this program reaches the agreed accounting gate.

## 2. Delivery Order

| Phase | Workstream | Outcome | Entry condition | Exit decision |
| --- | --- | --- | --- | --- |
| 0 | Scope and accounting truth matrix | One approved definition of supported events, expected postings, reports, roles, and test evidence | Current code and plans inventoried | Scope frozen and three representative datasets approved |
| 1 | Core accounting and close | GL, books, statements, controls, and close form a reproducible source of truth | Phase 0 approved | Accounting launch ready |
| 2 | Banking and treasury baseline | Statements, matching, settlements, payment batches, and cash position reconcile to GL | Phase 1 passed | Banking operations pilot ready |
| 3 | Advanced GST compliance | Returns and provider lifecycles reconcile to documents, tax ledgers, and GL | Phases 1-2 stable | Declared compliance scope launch ready |
| 4 | Procurement and three-way matching | Requisition-to-payment is governed through PO, receipt, invoice, and settlement | Phases 1-2 passed | Purchase-to-pay expansion launch ready |
| 5 | Order-to-cash and collections | Quote-to-settlement is governed through fulfilment, billing, credit, and collection | Phases 1-2 passed | Order-to-cash expansion launch ready |
| 6 | Deferred HRMS/payroll closure | Remaining employee operations and payroll product gaps are completed | Accounting priorities released | HRMS/payroll full-scope launch ready |

Only one major implementation phase may be active at a time. Discovery for the next phase may run in parallel without committing production schema or UI behavior.

## 3. Phase 0: Scope And Accounting Truth Matrix

Status: In progress

### Deliverables

- Inventory every supported accounting source: opening, journal, cash, bank, contra, sales, purchase, notes, receipts, payments, stock, manufacturing, assets, payroll, tax, and capital distribution.
- Define expected account classification, debit/credit lines, posting date, dimensions, subledger movement, inventory movement, tax effect, settlement effect, and reversal for each event.
- Map each event to daybook, ledger book, ledger summary, trial balance, trading account, P&L, balance sheet, cash/bank book, statutory register, and operational report.
- Classify routes and actions as `Supported`, `Conditional`, `Unsupported`, or `Backlog`.
- Define three independent certification datasets:
  - service entity with no inventory;
  - trading entity with GST, stock, receivables, and payables;
  - manufacturing entity with WIP, production, assets, and period close.
- Name positive, negative, permission, scope, duplicate, concurrency, rollback, and recovery scenarios for every supported event.

### Immediate First Slice

Build and execute the service-entity truth chain:

1. Opening capital and bank balance.
2. Taxable service sale and receipt allocation.
3. Taxable service purchase and payment allocation.
4. Expense accrual and reversal.
5. Cash/bank transfer.
6. Period close and reopen control.
7. Reconcile source documents to posting detail, daybook, ledger, trial balance, P&L, balance sheet, AR, AP, GST registers, and cash/bank balances.

### Exit Gate

- Every supported accounting event has an owner, expected result, and automated or manual evidence reference.
- The three datasets have approved opening balances and expected closing statements.
- Unsupported behavior is blocked or visibly described in the product.
- Accounting, engineering, QA, and operations approve the frozen scope.

## 4. Phase 1: Core Accounting And Close

### Development Scope

- Account master governance, classification, opening balances, immutable posting references, dimensions, and audit history.
- Journal, cash, bank, and contra lifecycle with confirm, approve where configured, post, reverse/unpost, and correction behavior.
- Allocation integrity for party and settlement accounts.
- Period locks, year-end close, retained earnings or capital distribution, controlled reopen, and prior-period adjustment.
- Consistent posted, reversed, and confirmed-only semantics in every report and posting-detail view.

### Certification Scope

- Source-to-journal-to-ledger-to-statement reconciliation for all three datasets.
- Branch, subentity, all-branch, FY, comparative-period, and custom-date behavior.
- Precision, rounding, negative and zero values, backdating, future dating, and closed-period validation.
- Duplicate click, retry, stale version, concurrent post/reverse, and interrupted request safety.
- Role, entity, branch, FY, export, print, attachment, and direct-API isolation.
- Desktop/mobile, Chromium/Firefox/WebKit, keyboard, accessibility, loading, empty, and error states.

### Exit Gate

- Debit equals credit for every active posting and reversal chain.
- Trial balance balances and balance-sheet equations reconcile exactly.
- P&L result rolls to equity according to the configured organization policy.
- AR, AP, inventory, assets, payroll, banking, and tax control accounts have no unexplained GL difference within supported scope.
- Three consecutive staging runs pass with no open S1/S2 issue.

## 5. Phase 2: Banking And Treasury Baseline

### Functional Slices

1. Bank masters, book-ledger mappings, signatories, limits, methods, and approval policies.
2. CSV/XLS statement import with duplicate detection, validation preview, commit, rollback, and retry.
3. One-to-one, split, one-to-many, and many-to-one matching; fees, interest, transfers, and unresolved queues.
4. Vendor, payroll, tax, refund, and transfer payment proposals and batches.
5. Cheque issue, print, deposit, clear, bounce, cancel, stale, and replacement lifecycle.
6. Cash position, short-term forecast, facilities, maturities, and treasury exceptions.

### Exit Gate

Statement closing balance, reconciliation report, cashbook, bank ledger, allocations, payment status, and GL agree exactly. Retried imports or payments cannot duplicate lines, settlements, or postings.

## 6. Phase 3: Advanced GST Compliance

### Functional Slices

1. Effective-dated GST registrations, HSN/SAC, rates, exemptions, RCM, ITC, and place-of-supply policy.
2. GSTR-1 preparation, validation, amendment, provider save, summary, filing, and status evidence.
3. GSTR-3B preparation, comparison, liability/credit validation, provider lifecycle, and filing evidence.
4. IMS/GSTR-2B import, matching, accept/reject/pending actions, ITC impact, period lock, and reconciliation.
5. E-invoice and e-way bill generation, cancellation, extension, polling, retry, outage, and audit evidence.
6. TDS/TCS returns, deposits, certificates, correction statements, notices, calendars, ownership, and audit packs.

### Exit Gate

Documents, GST/TDS/TCS registers, return summaries, provider acknowledgements, tax ledgers, payments, and GL reconcile for normal, amended, cancelled, retried, and prior-period cases.

## 7. Phase 4: Procurement And Three-Way Matching

### Functional Slices

1. Requisitions, budgets, approval limits, delegation, and rejection/revision workflow.
2. RFQs, vendor quotations, normalized comparison, selection evidence, and approval.
3. Purchase orders, contracts, blanket orders, releases, amendments, and closure.
4. Goods/service receipts, inspection, rejection, return, short/excess receipt, and landed cost.
5. Two-way and three-way matching with configurable quantity, price, tax, freight, and date tolerances.
6. Exception workbench, GRNI clearing, invoice approval, payment readiness, and vendor evaluation.

### Exit Gate

Commitment, budget, PO, receipt, inspection, invoice/note, GRNI, inventory/expense, AP, payment, tax, and GL reconcile for complete, partial, excess, rejected, returned, and cancelled scenarios.

## 8. Phase 5: Order-To-Cash And Collections

### Functional Slices

1. Quotations, versions, pricing, discounts, approvals, expiry, conversion, and loss reasons.
2. Sales orders, contracts, availability, reservation, allocation, hold, amendment, and cancellation.
3. Picking, dispatch, delivery challan, proof of delivery, return, short delivery, and replacement.
4. Advance, milestone, recurring, usage, consolidated, and final billing.
5. Credit limits, overdue holds, exception approvals, collection queues, promises, disputes, dunning, and write-offs.
6. Customer statements and self-service access to invoices, credits, receipts, allocations, and balances.

### Exit Gate

Quotation/order, fulfilment, stock, invoice/note, revenue/COGS, GST, AR, receipt/allocation, customer statement, collections status, and GL reconcile across complete and exceptional flows.

## 9. Phase 6: Deferred HRMS And Payroll Closure

Return to the approved payroll backlog for effective-dated transfers and promotions, attendance/leave integration, employee bank/emergency/document data, reimbursements, expanded ESS, bank-specific payment files, full-and-final operations, statutory completion, and final certification.

## 10. Common Definition Of Done

A phase is complete only when:

- Business lifecycle and state transitions are complete and auditable.
- Posting, reversal, allocation, inventory, tax, and reports agree.
- APIs enforce permissions and tenant/entity/branch/FY scope independently of the UI.
- Duplicate, concurrency, timeout, retry, rollback, and recovery behavior is proven.
- Desktop, mobile, browser, keyboard, accessibility, export, print, empty, loading, and failure states pass.
- Migrations, observability, support diagnostics, backup/restore, and rollback are rehearsed.
- The phase matrix records passed evidence, known risks, owners, waivers, and release recommendation.

## 11. Status Register

| Phase | Status | Current action | Blocking decision |
| --- | --- | --- | --- |
| 0. Scope and truth matrix | Local complete; staging pending | Dataset A, all six Dataset B variants, and Dataset C manufacturing/assets now pass fixed local oracles. Repeat decisive evidence on staging. | Staging scope and execution window |
| 1. Core accounting and close | In progress | Certify the completed truth matrix on staging, then run close/reopen and repeated launch gates | Phase 0 staging evidence |
| 2. Banking and treasury | Discovery allowed | Reuse current bank-reconciliation foundation; inventory missing payment/treasury workflows | Phase 1 accounting gate |
| 3. Advanced GST | Discovery allowed | Reconcile current report/provider implementation against the required lifecycle | Stable accounting and banking controls |
| 4. Procurement | Planned | Charter and domain design only | Phases 1-2 launch ready |
| 5. Order-to-cash | Planned | Charter and domain design only | Phases 1-2 launch ready |
| 6. HRMS/payroll closure | Paused | Preserve backlog and current supported scope | Accounting-first phases released |

## 12. Update Log

| Date | Change | Result |
| --- | --- | --- |
| 14 September 2026 | Created the accounting-first completion program and began Phase 0. | Core accounting is the active workstream; HRMS/payroll completion is paused; banking and GST discovery may proceed. |
| 14 September 2026 | Defined the service-entity accounting oracle and ran the focused accounting baseline. | 250/250 local tests passed; dedicated source-to-report reconciliation automation is next. |
| 14 September 2026 | Implemented Dataset A as an isolated cross-report integration test and reran the full focused baseline. | 251/251 passed; lifecycle, subledger, and GST extensions are the next Phase 0 slice. |
| 14 September 2026 | Linked Dataset A to real sales/purchase open items and settlements and added lifecycle-state assertions. | 253/253 passed; AR/AP and active-versus-inactive report semantics reconcile, leaving GST and browser evidence for Dataset A. |
| 14 September 2026 | Added statutory register-to-control-ledger assertions and corrected the GSTR-1 annotation conflict discovered by the oracle. | Dataset A passed 4/4 and the expanded accounting/GSTR-1 pack passed 321/321; browser workflow and variant coverage are next. |
| 14 September 2026 | Added a deterministic Dataset A browser contract for Daybook, Trial Balance, Ledger Summary, P&L, and Balance Sheet, then reran the broader seeded report suite. | The contract passed 6/6 across Chromium, Firefox, and WebKit and the seeded Chromium suite passed 13/13; live source creation, staging execution, and variants remain the Phase 0 gate. |
| 14 September 2026 | Ran unmocked local browser flows for cash, bank, journal, sales/receipt, and purchase/payment. | Each business flow has passing evidence, but the combined sequential run exposed report/navigation stalls and cannot yet serve as launch evidence. Performance stabilization plus the three remaining Dataset A event types are next. |
| 14 September 2026 | Stabilized report navigation and completed named capital-introduction, accrual/reversal, and bank-to-cash contra browser scenarios. | Sequential source/report coverage passed 6/6 in 5.8 minutes and the three-event accounting run passed 4/4 in 1.9 minutes. Strict opening-balance and staging certification remain. |
| 14 September 2026 | Completed strict opening-balance master and cross-report certification. | The Ledger Book now applies the same entity-opening inheritance policy as Trial Balance and Balance Sheet under branch scope. Financial-books tests passed 82/82 and the live Chromium opening workflow passed 2/2; only staging repetition and Dataset B/C scope approval remain for Phase 0. |
| 14 September 2026 | Froze and automated the Dataset B trading baseline. | Purchase and sales documents plus returns, FIFO stock, direct freight, GST, settlements, Trading Account, P&L, Trial Balance, and Balance Sheet reconcile to fixed expected values. The combined focused regression passed 185/185; Dataset B variants and Dataset C remain open. |
| 14 September 2026 | Completed Dataset B landed-cost and layered-valuation Variant 1. | Capitalized purchase expenses now preserve balanced GL posting and feed item valuation; FIFO and moving-average closing stock, COGS, and gross-profit oracles pass with product-filtered report scope. |
| 14 September 2026 | Completed Dataset B discount, tax-inclusive pricing, CESS, and round-off Variant 2. | Both document calculators and posting adapters follow the fixed monetary sequence, while inventory, GST controls, Trial Balance, Trading Account, and P&L reconcile in the 249-test focused pack. |
| 14 September 2026 | Completed Dataset B batch/location and partial-return Variant 3. | Inventory valuation now preserves product/location/batch cost pools across all five methods, strict and controlled negative-stock policies are explicit, and stock reports reconcile location totals to entity totals. The expanded purchase, sales, inventory-report, and accounting-oracle pack passed 569/569. |
| 14 September 2026 | Completed Dataset B settlement and advance Variant 4. | Split receipts/payments, partial advance use, residual unapplied balances, operational AR/AP reports, and party control ledgers reconcile. Settlement services now cap tolerated rounding differences to the exact available balance; the settlement/report pack passed 293/293 and the expanded regression passed 570/570. |
| 14 September 2026 | Completed Dataset B IGST and taxability Variant 5. | Inter-state taxable, exempt, nil-rated, and non-GST purchase/sales streams reconcile across statutory returns, operational registers, tax controls, FIFO inventory, Trial Balance, Trading Account, and P&L. The statutory/reporting pack passed 186/186 and the expanded regression passed 571/571; lifecycle/concurrency is the remaining Dataset B variant. |
| 14 September 2026 | Completed Dataset B lifecycle and concurrency Variant 6. | Row-locked purchase/sales transitions, HTTP 409 stale-version rejection, idempotent terminal retries, and single-reversal guarantees pass in the 1,011-test backend matrix. The focused Angular lifecycle pack passed 822 with one existing skip and the development build passed; Dataset C and staging repetition are next. |
| 14 September 2026 | Completed the local Dataset C manufacturing and asset truth oracles. | Actual-cost production, capitalized overhead, by-product recovery, finished-goods COGS, downstream-safe reversal, closed-year rejection, asset capitalization, depreciation, P&L, Trial Balance, Balance Sheet, and depreciation cancellation reconcile. The oracle exposed and corrected production value-added COGS and contra-asset/current-loss presentation defects; the full affected regression passed 223/223. Staging certification is next. |
| 15 September 2026 | Began Dataset C staging certification. | Manufacturing passed 24/24, including concurrency and reconciliation. Asset certification exposed a CWIP capitalization transfer defect; the staging record was reversed and the local fix passes 224/224. Deploy and rerun the asset lifecycle before closing Phase 0. |
