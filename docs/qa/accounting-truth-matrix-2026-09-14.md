# Accounting Truth Matrix

Status: Phase 0 baseline in progress

Last updated: 15 September 2026

Execution plan: [Accounting-First Product Completion Plan](../product/accounting-first-completion-plan-2026-09-14.md)

## Purpose

This register is the accounting oracle for source-to-report certification. Amounts below are fixed expected results, not values copied from application reports after execution.

## Scenario Completeness Register

This section is the guardrail against missed launch scenarios. A scenario is considered launch-covered only when it is either:

- directly asserted in this truth-matrix dataset,
- asserted by a named linked backend/browser suite, or
- explicitly listed as a product extension/backlog item rather than silently assumed.

| Area | Required scenario | Coverage status | Evidence owner |
| --- | --- | --- | --- |
| Source-to-posting | Opening balance, journal, receipt, payment, contra, sales invoice, purchase invoice, sales return, purchase return | Covered | Dataset A, Dataset B, live source-document browser workflows |
| Source lifecycle | Draft/confirmed, posted, reversed/unposted, cancelled, duplicate retry, stale browser version, rapid double-click | Covered | Dataset A lifecycle proof, Dataset B Variant 6, commercial lifecycle/recovery certificates |
| Posting state presentation | Active reports exclude draft/reversed entries; non-posted view exposes draft/reversed records without polluting TB/P&L/BS | Covered | Dataset A lifecycle-state proof and purchase-register posting-detail correction evidence |
| Document date versus posting date | Document/report filters and posting-detail filters preserve the intended date basis | Covered for core commercial reports; keep in regression | Purchase-register, sales-register, daybook, ledger, and live report evidence |
| Financial-year and branch scope | Entity, FY, branch/subentity, all-branch, and branch-inherited opening balance behavior | Covered | Dataset A staging source mutation gate, Ledger Book opening-scope regression, live staging report matrix |
| Party subledger | AR invoice, receipt allocation, customer advance, partial application, AP bill, payment allocation, vendor advance, over-allocation block | Covered | Dataset A AR/AP proof, Dataset B Variant 4, expanded AR/AP settlement certificate |
| GST intra-state | CGST/SGST output, input, control ledgers, GSTR-1, purchase register, net liability | Covered | Dataset A GST proof and Dataset B baseline |
| GST inter-state | IGST input/output, no CGST/SGST leakage, registers, GSTR-1 and GSTR-3B | Covered | Dataset B Variant 5 |
| Taxability classes | Taxable, exempt, nil-rated, non-GST, unregistered/B2C where legally supported | Covered | Dataset B Variant 5 plus commercial taxability preservation certificate |
| Reverse charge and blocked/ineligible ITC | Posting, report classification, and ledger impact | Covered by purchase/GST focused suites; keep in release pack | Purchase statutory, register, and GST regression suites referenced by commercial baseline |
| HSN/SAC controls | Required where GST/business rule needs it; allowed exceptions for non-GST/unregistered/service policy are explicit | Covered by invoice validation/browser certificates; keep in release pack | Commercial document reconciliation and GST symmetry matrix |
| TDS/TCS | Invoice-stage and payment/receipt-stage withholding, payable ledgers, report visibility, reversal | Covered by withholding and voucher lifecycle suites; keep in release pack | Withholding, payment-voucher, receipt-voucher, sales-contract evidence |
| Discounts and tax-inclusive pricing | Discount-before-tax, tax-inclusive back-calculation, CESS, round-off, inventory cost exclusion of recoverable tax | Covered | Dataset B Variant 2 |
| Inventory valuation | FIFO, LIFO, moving average, periodic weighted average, latest cost, batch/location isolation, negative stock truthfulness | Covered | Inventory identity tests, Dataset B Variant 3, staging inventory reports |
| Trading account | Opening/inflows/issues/closing-stock scope parity, COGS, gross profit, stock valuation mode | Covered | Dataset B baseline and Variants 1, 3, 5 |
| Manufacturing | Material consumption, by-product recovery, additional cost, WIP, finished output, downstream-sale reversal block, closed-period block | Covered | Dataset C oracle and manufacturing report correctness suite |
| Fixed assets | Purchase-to-asset intake, CWIP transfer, capitalization, depreciation, reversal, disposal ordering | Covered for pilot; disposal/impairment broader matrix remains release-pack regression | Dataset C asset extension and asset service regressions |
| Financial statements | Trial Balance, Daybook, Ledger Book/Summary, Cash/Bank Book, P&L, Trading Account, Balance Sheet | Covered | Dataset A/B/C, ledger scope regression, live staging report matrix |
| Output/export | CSV/XLSX/PDF/print content, filenames, filter scope, mobile/tablet preview usability | Partially covered; remaining surfaces must stay in Phase 7 gate | Purchase-register output, sales print certificates, financial statement output certificate, payables export certificate, receivables export certificate, voucher PDF certificate |
| Accessibility/keyboard | WCAG automated checks, focusable scroll regions, keyboard access to exports/dialogs | Partially covered; full screen-reader pass remains launch gate | Financial statement output/accessibility certificate |
| Failure/recovery | 401/403/409/422/429/500, timeout, disconnect/offline, interrupted upload/download, lost commit response | Covered for certified commercial flows; infrastructure restore remains launch dependency | Commercial failure/recovery certificates |
| Concurrency/data protection | Concurrent post/reverse/settlement, idempotent retry, closed period locks, destructive close/rollback cleanup | Covered for certified flows; isolated DB restore rehearsal remains launch dependency | Dataset B Variant 6, controls destructive workflow, commercial concurrency evidence |
| Multi-organization formations | Proprietorship, company, partnership/LLP with capital distribution, profit appropriation, partner remuneration/interest | Partially covered; advanced appropriation is a product roadmap item, not pilot accounting sign-off | Capital-distribution plan and static-account evidence |
| Payroll accounting | Salary payable, statutory deductions, reimbursements, FnF posting, reconciliation to ledgers | P1 covered enough for accounting focus; keep HRMS/payroll backlog open | Payroll readiness plan and backend backlog |
| Banking/treasury | Bank book, cash book, receipt/payment vouchers, bank reconciliation baseline | Covered for pilot; automated bank feeds/payment batches are product expansion | Banking regression and product roadmap |

No unlisted accounting-significant scenario should be added to pilot scope without either adding an oracle row here or explicitly documenting it as a post-pilot product extension.

## Dataset A: Service Entity

Assumptions:

- Indian registered entity and registered counterparties.
- Intra-state supplies using CGST 9% and SGST 9%.
- Accrual accounting, INR functional currency, no opening receivable or payable.
- All transactions occur in one open financial year and one branch.
- The purchase service is fully ITC eligible.

### Event Expectations

| Step | Business event | Debit | Credit | Expected operational effect |
| --- | --- | --- | --- | --- |
| A1 | Opening capital funded into bank, 100,000.00 | Bank 100,000.00 | Owner capital 100,000.00 | Bank book opening 100,000.00 |
| A2 | Service sale, taxable value 10,000.00 | Customer 11,800.00 | Service revenue 10,000.00; Output CGST 900.00; Output SGST 900.00 | AR 11,800.00; GSTR-1 taxable 10,000.00 and tax 1,800.00 |
| A3 | Full customer receipt and allocation | Bank 11,800.00 | Customer 11,800.00 | Customer outstanding zero; allocation fully settled |
| A4 | Service purchase, taxable value 4,000.00 | Service expense 4,000.00; Input CGST 360.00; Input SGST 360.00 | Vendor 4,720.00 | AP 4,720.00; eligible ITC 720.00 |
| A5 | Full vendor payment and allocation | Vendor 4,720.00 | Bank 4,720.00 | Vendor outstanding zero; allocation fully settled |
| A6 | Expense accrual, 1,500.00 | Accrued expense 1,500.00 | Accrued liability 1,500.00 | Liability and period expense increase 1,500.00 |
| A7 | Full reversal of A6 | Accrued liability 1,500.00 | Accrued expense 1,500.00 | Accrual and its P&L effect return to zero |
| A8 | Transfer from bank to cash, 5,000.00 | Cash 5,000.00 | Bank 5,000.00 | Total cash unchanged; bank decreases and cash increases |

### Closing Oracle

| Measure | Expected value |
| --- | ---: |
| Bank | 102,080.00 debit |
| Cash | 5,000.00 debit |
| Customer receivable | 0.00 |
| Vendor payable | 0.00 |
| Output GST | 1,800.00 credit |
| Input GST | 720.00 debit |
| Net GST liability | 1,080.00 credit |
| Revenue | 10,000.00 credit |
| Expense | 4,000.00 debit |
| Net profit | 6,000.00 credit |
| Capital before current profit | 100,000.00 credit |
| Closing gross assets (bank, cash, and input GST) | 107,800.00 debit |
| Closing liabilities plus equity including profit | 107,800.00 credit |
| Closing net assets after output GST liability | 106,000.00 |
| Trial-balance difference | 0.00 |
| Balance-sheet difference | 0.00 |

### Report Assertions

| Surface | Required assertion |
| --- | --- |
| Posting detail | Each source shows only its active posting state; reversal links to A6 and does not masquerade as an active posting |
| Daybook | A2-A8 appear once with correct dates, references, debit, credit, and lifecycle state; A1 remains an opening-control/TB event rather than an ordinary daybook voucher |
| Ledger book | Every ledger movement agrees with the event table and running balance |
| Ledger summary | Closing balances agree with the closing oracle |
| Trial balance | Total debit equals total credit and difference is 0.00 |
| Profit and loss | Revenue 10,000.00, expense 4,000.00, net profit 6,000.00 |
| Balance sheet | Gross assets and liabilities/equity both equal 107,800.00; net assets after the GST liability equal 106,000.00 |
| Cash/bank book | Bank 102,080.00 and cash 5,000.00 |
| Receivables | Invoice 11,800.00, receipt/allocation 11,800.00, outstanding 0.00 |
| Payables | Invoice 4,720.00, payment/allocation 4,720.00, outstanding 0.00 |
| GST reports | Output 1,800.00, eligible input 720.00, net liability 1,080.00 |

### Required Variants

- A3 and A5 as partial, split, excess, advance, and unallocated settlement.
- Inter-state equivalent using IGST 18%.
- Unregistered and non-GST counterparty where legally supported.
- Exempt, nil-rated, non-GST, reverse-charge, and ineligible-ITC purchase permutations.
- Branch-specific and all-branch reports.
- Confirmed-only, posted, reversed, cancelled, and corrected source states.
- Closed-period, stale-version, duplicate-click, retry-after-timeout, and concurrent post/reverse attempts.

## Dataset B: Trading Entity

Status: Baseline plus landed-cost/layered-valuation Variant 1, discount/tax/CESS Variant 2, batch/location/partial-return Variant 3, settlement/advance Variant 4, IGST/taxability Variant 5, and lifecycle/concurrency Variant 6 automated locally. Staging inventory report reconciliation and concurrency certification are complete.

Assumptions:

- Indian registered entity and registered counterparties using intra-state GST at 18%.
- One non-batch trading product, FIFO valuation, INR functional currency, and one branch.
- Opening capital of 100,000.00 is deposited into bank; opening stock is zero.
- Inbound freight is a direct trading expense and is not capitalized into item cost in this baseline.
- Purchase and sales returns affect both inventory and GST.

### Event Expectations

| Step | Business event | Accounting and stock expectation |
| --- | --- | --- |
| B1 | Opening bank/capital 100,000.00 | Bank Dr 100,000.00; Capital Cr 100,000.00 |
| B2 | Buy 100 units at 120.00 plus CGST/SGST 9% | Purchases Dr 12,000.00; Input CGST/SGST Dr 1,080.00 each; Vendor Cr 14,160.00; stock +100 at 120.00 |
| B3 | Pay inbound freight 1,200.00 | Carriage Inward Dr 1,200.00; Bank Cr 1,200.00 |
| B4 | Return 10 units from B2 | Vendor Dr 1,416.00; Purchase Returns Cr 1,200.00; Input CGST/SGST Cr 108.00 each; stock -10 at 120.00 |
| B5 | Sell 80 units at 200.00 plus CGST/SGST 9% | Customer Dr 18,880.00; Sales Cr 16,000.00; Output CGST/SGST Cr 1,440.00 each; stock -80 at 120.00 |
| B6 | Customer returns 5 units from B5 | Sales Returns Dr 1,000.00; Output CGST/SGST Dr 90.00 each; Customer Cr 1,180.00; stock +5 at 120.00 |
| B7 | Collect the net customer balance | Bank Dr 17,700.00; Customer Cr 17,700.00; receivable closes |
| B8 | Pay the net vendor balance | Vendor Dr 12,744.00; Bank Cr 12,744.00; payable closes |

### Closing Oracle

| Measure | Expected value |
| --- | ---: |
| Closing quantity | 15 units |
| Closing inventory | 1,800.00 debit |
| Net sales | 15,000.00 credit |
| Net purchases | 10,800.00 debit |
| Inbound freight | 1,200.00 debit |
| COGS | 10,200.00 |
| Gross and net profit | 4,800.00 credit |
| Customer receivable | 0.00 |
| Vendor payable | 0.00 |
| Input GST | 1,944.00 debit |
| Output GST | 2,700.00 credit |
| Net GST liability | 756.00 credit |
| Bank | 103,756.00 debit |
| Assets | 107,500.00 debit |
| Liabilities plus equity including profit | 107,500.00 credit |
| Trial-balance difference | 0.00 |
| Balance-sheet difference | 0.00 |

### Variant 1: Capitalized Landed Cost And Multiple Cost Layers

| Event or result | FIFO oracle | Moving-average oracle |
| --- | ---: | ---: |
| Layer 1: 100 units including allocated landed cost | 11,000.00 at 110.00/unit | 11,000.00 at 110.00/unit |
| Layer 2: 50 units including allocated landed cost | 9,000.00 at 180.00/unit | 9,000.00 at 180.00/unit |
| Sale/issue | 120 units | 120 units |
| Closing quantity | 30 units | 30 units |
| Closing inventory | 5,400.00 | 4,000.00 |
| COGS | 14,600.00 | 16,000.00 |
| Sales | 30,000.00 | 30,000.00 |
| Gross profit | 15,400.00 | 14,000.00 |

Capitalized header expenses remain a debit in the periodic purchase journal so the vendor-inclusive document stays balanced. The expense is also allocated into inventory movement unit cost; closing-stock valuation then defers the unconsumed portion. Product-filtered Trading Account runs must apply the same product filter to opening, inflows, and closing stock.

### Variant 2: Discount, Tax-Inclusive Pricing, CESS, And Round-Off

Both purchase and sales line calculations use the following fixed sequence and oracle:

| Measure | Expected value |
| --- | ---: |
| Gross: 10 units at 118.00 | 1,180.00 |
| Percentage discount at 10% | 118.00 |
| Discounted tax-inclusive amount | 1,062.00 |
| Taxable value after backing out 18% GST | 900.00 |
| CGST / SGST | 81.00 / 81.00 |
| Composite CESS: 2% of taxable plus 1.00 per unit | 28.00 |
| Unrounded document total | 1,090.00 |
| Purchase round-off and payable | +0.25 / 1,090.25 |
| Sales round-off and receivable | -0.20 / 1,089.80 |
| Inventory unit cost, excluding recoverable GST/CESS | 90.00 |

For the cross-report scenario, 10 units are purchased and 5 units sold. Closing stock and COGS are both 450.00, gross profit is 450.00, combined round-off expense is 0.45, and net profit is 449.55. Dedicated tax-control ledgers and party balances produce Trial Balance closing totals of 2,180.25 debit and credit.

### Variant 3: Batch, Location, Partial Returns, And Stock Policy

| Event or result | Location A / LOT-A | Location B / LOT-B | Entity total |
| --- | ---: | ---: | ---: |
| Purchase receipt | 100 units at 100.00 | 50 units at 120.00 | 150 units / 16,000.00 |
| Partial purchase return | - | 10 units at 120.00 | -10 units / -1,200.00 |
| Sale issue | 30 units at 100.00 | - | -30 units / -3,000.00 |
| Partial sales return | 5 units at 100.00 | - | +5 units / +500.00 |
| Closing stock | 75 units / 7,500.00 | 40 units / 4,800.00 | 115 units / 12,300.00 |

Valuation pools are isolated by product, location, and batch for FIFO, LIFO, moving average, periodic weighted average, and latest-cost reports. Stock in another location cannot authorize a sale or purchase return. Strict mode blocks a shortage even if the generic negative-stock flag is enabled; controlled mode permits it only when `allow_negative_stock` is enabled and the stock hint warns the user. An uncovered negative balance remains visible as negative quantity with zero invented inventory value.

### Variant 4: Split Settlement, Advances, And Control-Ledger Reconciliation

| Event or result | Receivables oracle | Payables oracle |
| --- | ---: | ---: |
| Source document | Invoice 10,000.00 | Bill 8,000.00 |
| Two cash settlements | 3,000.00 + 2,000.00 | 2,500.00 + 1,500.00 |
| Advance received/paid | 1,500.00 | 1,000.00 |
| Advance applied | 500.00 | 400.00 |
| Gross open item after allocations | 4,500.00 | 3,600.00 |
| Residual unapplied advance | 1,000.00 | 600.00 |
| Net report exposure | 3,500.00 | 3,000.00 |
| Party control ledger | 3,500.00 debit | 3,000.00 credit |

The real AR/AP services create and post all four allocations, update both open items and advances, and feed the customer/vendor outstanding reports. Attempts more than one cent above the remaining allocatable amount are blocked without mutation. Inputs inside the one-cent comparison tolerance are capped to the exact outstanding or advance balance, so `settled_amount` and `adjusted_amount` can never exceed their source balances.

### Variant 5: Inter-State IGST And Non-Taxable Supplies

| Measure | Purchase oracle | Sales oracle |
| --- | ---: | ---: |
| Taxable inter-state value | 10,000.00 | 8,000.00 |
| IGST | 1,800.00 input | 1,440.00 output |
| Exempt value | 1,000.00 | 800.00 |
| Nil-rated value | 400.00 | 300.00 |
| Non-GST value | 100.00 | 150.00 |
| Total register base value | 11,500.00 | 9,250.00 |
| Party control balance | 13,300.00 credit | 10,690.00 debit |

The taxable documents use an inter-state 18% IGST regime with no CGST or SGST. Exempt, nil-rated, and non-GST documents retain their distinct classifications and carry zero tax. GSTR-1's nil/exempt summary reports 800.00, 300.00, and 150.00 separately. GSTR-3B reports 8,000.00 and 1,440.00 as taxable outward value and IGST, 1,250.00 as outward nil/exempt/non-GST value, 150.00 as the non-GST subset, 1,800.00 as available input IGST, and 1,500.00 as inward exempt/nil/non-GST value.

The same events receive 135 units and issue 60. FIFO therefore closes 75 units at 5,500.00, recognizes COGS of 6,000.00, and reports gross/net profit of 3,250.00. The six isolated accounting ledgers balance at 23,990.00 per side.

### Variant 6: Lifecycle, Retry, And Concurrency Protection

Purchase and sales invoice lifecycle endpoints now expose and accept the server `updated_at` version. Confirm, post, unpost/reverse, and cancel acquire a database row lock before transition; a stale browser version receives HTTP 409 with the `stale_object` code before any document, posting, inventory, tax, or subledger mutation.

Completed-action retries are idempotent. Repeating confirm, post, or cancel returns the terminal document without reallocating numbers or recreating accounting effects. Repeating unpost/reverse after a response timeout returns the already-reversed document and does not create a second reversal batch. Existing API callers that do not yet send a version retain their prior request contract, while purchase invoice and note screens plus both sales line modes forward the version from hydrated invoice responses.

The expanded backend matrix passed 1,011/1,011 across purchase, sales, posting, books, payables, receivables, invoice contracts, and the accounting truth dataset. The focused Angular invoice lifecycle pack passed 822 tests with one existing skip, and the development build completed successfully.

## Dataset C: Manufacturing Entity

Status: Local numeric oracle complete; staging manufacturing and fresh purchase-to-asset lifecycle certification passed. One historical pre-fix purchase record remains queued for data remediation.

The fixed actual-cost oracle uses opening raw-material stock of `4,700.00`, consumes
`470.00`, absorbs `50.00` of production cost, recognizes a `10.00` by-product,
and capitalizes `510.00` into the main finished output. Production closing stock is
`4,750.00`. A sale of four units at `51.00` records `204.00` inventory cost and
leaves closing stock of `4,546.00`.

The same test requires material-consumption, output/yield, posting-audit, and WIP
reports to agree on the work-order values; requires the manufacturing journal to
balance; prevents work-order reversal while the finished output has a downstream
sale; returns stock to the `4,700.00` opening position after dependent reversal;
and proves a closed financial year cannot recreate stock or accounting rows.

The asset extension capitalizes `5,000.00`, posts `83.33` April depreciation,
reconciles `4,916.67` net book value through Trial Balance, Profit & Loss, and
Balance Sheet, and then proves cancellation removes the depreciation effect while
preserving capitalization. The standard-cost test separately fixes expected
material variance at `9.00` and yield variance at `9.40`.

Local certification also corrected two defects found by the oracle: operational
COGS now includes net value added by production, and Balance Sheet presentation
nets accumulated depreciation against assets while current-period losses reduce
equity. Incremental partial finished-goods receipts, explicit material-return
documents, and substitution lineage remain documented product extensions rather
than supported behavior.

## Evidence Register

| Evidence | Status | Reference or next action |
| --- | --- | --- |
| Scenario completeness register | Complete locally | Added 16 September 2026. All pilot-significant accounting scenarios are explicitly mapped to direct oracle tests, linked evidence, partial launch gates, or post-pilot product extensions. Focused `reports.tests_accounting_truth_matrix` passed 12/12 after the register update. |
| Existing posting, ledger, and GSTR-1 baseline | Complete locally | Combined accounting run passed 321/321 on 14 September 2026, including all current Dataset A and dedicated GSTR-1 tests |
| Dataset A backend fixture and reconciliation test | Complete locally | `reports.tests_accounting_truth_matrix.ServiceEntityAccountingTruthMatrixTests` proves daybook, ledger summary, trial balance, P&L, and balance sheet from one source set |
| Dataset A lifecycle-state proof | Complete locally | Draft and reversed entries remain visible in the non-posted daybook but are excluded from active daybook, TB, P&L, and balance sheet totals |
| Dataset A AR/AP allocation proof | Complete locally | Real sales/purchase headers, open items, and posted settlement lines prove pre-settlement exposure, full settlement, and zero AR/AP control-ledger balances |
| Dataset A GST register and control-ledger proof | Complete locally | GSTR-1 output 1,800.00, eligible purchase-register input 720.00, and net GST liability 1,080.00 reconcile to the four GST control ledgers |
| Dataset A Playwright presentation contract | Complete locally | `tests/p1/accounting-truth-matrix.p1.spec.ts` in `finacc-ui-tests` renders the fixed Dataset A oracle through Daybook, Trial Balance, Ledger Summary, P&L, and Balance Sheet; 6/6 setup/browser projects passed across Chromium, Firefox, and WebKit |
| Existing seeded financial browser regression | Complete locally | `tests/p1/financial-data-integrity-seeded.p1.spec.ts` passed 13/13 on Chromium after aligning the closing-balance assertion with the UI's normalized balance format |
| Dataset A live source-document browser workflow | Complete locally | Real opening-balance masters, cash, bank, journal, sales-to-receipt, purchase-to-payment, capital introduction, named-ledger accrual/reversal, and bank-to-cash contra flows pass. |
| Dataset A sequential browser launch run | Complete locally | The six-test Chromium source/report sequence passed 6/6 in 5.8 minutes after eliminating a redundant post-settlement Open Items reload and cancelling stale report subscriptions. |
| Dataset A named accounting events | Complete locally | `FIN-ACCT-LIVE-001..003` passed together 4/4 in 1.9 minutes: Bank/Opening Equity capital journal, Rent/Salary Payable accrual plus unpost, and Cash/Bank contra plus cashbook proof. |
| Dataset A strict opening-balance browser workflow | Complete locally | `FIN-ACCT-OPEN-001` passed in Chromium: negative standalone-ledger opening validation, Bank debit and Capital credit account openings, Trial Balance balance, Balance Sheet classification, Daybook exclusion, branch-scoped Ledger Book inheritance, and cleanup were verified end to end. |
| Ledger Book opening-scope regression | Complete locally | `reports.tests_books` passed 82/82. Full-FY books include posted opening rows, custom periods carry openings separately, and a selected branch inherits entity-level openings without admitting ordinary activity from other branches. |
| Dataset A live staging report matrix | Complete | `FIN-FIN-LIVE-001..007` passed as one 24/24 run across Chromium, Firefox, and WebKit on 15 September 2026. Trial Balance, Ledger Summary, P&L, Trading Account, Balance Sheet, Daybook, Cashbook, and diagnostic accounting relationships matched their live API/component state. |
| Dataset A staging source mutation gate | Complete | After deploying the stale code-series correction, `FIN-ACCT-OPEN-001` passed 2/2 in Chromium on staging. Negative opening validation, Bank debit and Capital credit openings, balanced Trial Balance, Balance Sheet classification, Daybook exclusion, both Ledger Books at 100,000.00, and cleanup all passed. |
| Dataset B fixed oracle | Complete locally | `TradingEntityAccountingTruthMatrixTests` proves posted source invoices/credit notes, FIFO quantity/value, Daybook, Ledger Summary, Trial Balance, Trading Account, P&L, Balance Sheet, GST registers/control ledgers, and zero party-ledger balances after settlement. |
| Dataset B Variant 1 | Complete locally | Capitalized header expenses balance the purchase journal and increase inventory unit cost; two landed-cost layers reconcile closing stock, COGS, and gross profit under FIFO and moving-average valuation. The focused accounting, register, GSTR-1, books, and purchase-adapter pack passed 199/199. |
| Dataset B Variant 2 | Complete locally | Discount-before-tax ordering, tax-inclusive back-calculation, composite CESS, positive purchase round-off, negative sales round-off, inventory cost, Trial Balance, Trading Account, and P&L reconcile to fixed values. The expanded focused regression passed 249/249. |
| Dataset B Variant 3 | Complete locally | Two locations and two batches prove exact-pool valuation, partial purchase/sales returns, entity-to-location reconciliation, no cross-location stock borrowing, strict shortage blocking, controlled negative-stock behavior, and truthful negative quantity reporting. The expanded regression passed 569/569. |
| Dataset B Variant 4 | Complete locally | Split receipts/payments, residual customer/vendor advances, partial advance applications, over-allocation rollback, AR/AP reports, party control ledgers, Trial Balance, and Daybook reconcile. The settlement/report pack passed 293/293 and the expanded purchase, sales, inventory, and accounting regression passed 570/570. |
| Dataset B Variant 5 | Complete locally | Inter-state purchases and sales plus exempt, nil-rated, and non-GST streams reconcile across operational registers, GSTR-1, GSTR-3B, GST control ledgers, inventory, Trial Balance, Trading Account, and P&L. The statutory/reporting pack passed 186/186 and the expanded purchase, sales, inventory, and accounting regression passed 571/571. |
| Dataset B Variant 6 | Complete locally | Purchase and sales lifecycle transitions use row locks and optional server-version checks; stale clients receive HTTP 409, terminal retries remain successful, and repeated unpost/reverse does not create duplicate reversal batches. Backend passed 1,011/1,011; focused Angular lifecycle coverage passed 822 with one existing skip; the frontend development build passed. |
| Dataset B remaining variants | Complete | All six planned trading-entity variants have local automated evidence, and the staging inventory report and concurrency gates are complete. |
| Dataset B staging inventory reports | Complete | After deployment of the deficit-ordering correction, `FIN-INV-XREP-001..003` and `FIN-INV-NREC-001..004` passed 24/24 across Chromium, Firefox, and WebKit in 4.3 minutes. Stock Summary, Stock Ledger, Stock Aging, Non-Moving Stock, Stock Day Book, Control, and Book drilldowns now preserve scope and reconcile quantities, including Product X1 at 107 units. |
| Dataset B staging inventory exports | Complete | `inventory.live.spec.ts` now validates Stock Summary, Stock Ledger, Stock Aging, Stock Movement, Location Stock, Stock Day Book, Stock Book Summary, Stock Book Detail, Non-Moving Stock, Slow Moving vs Dead Stock, and Reorder Status export payloads. Focused Chromium staging runs passed 4/4 on 16 September 2026, including usable Excel, CSV, PDF, and print output for all implemented inventory report export surfaces. |
| Dataset B staging concurrency | Complete | `FIN-INV-CONC-STG-001..002` passed 3/3 including setup on Chromium. Simultaneous adjustment and transfer posts produced one posting outcome, and every temporary transfer, seed adjustment, and accounting effect was unposted and cancelled by verified cleanup. |
| Core accounting controls and close | Complete for pilot gate | The focused backend close, opening, permission, destructive-workflow, and financial-year lock gate passed 37/37. The staging controls surface certificate passed 45/45 across Chromium, Firefox, and WebKit in 5.2 minutes. The final isolated destructive staging certificate passed 2/2 in 1.0 minute, proving actual close, duplicate-close rejection, closed-period posting rejection, UI opening carry-forward generation, source-FY retention, visible UI rollback, duplicate-opening rejection, rollback ordering, opening-entry purge, close rollback, restored open/readiness state, and zero temporary user/entity residue. The focused frontend component suite passes 25/25. |
| Core financial statement output and accessibility | Local correction ready; staging rerun pending | Trial Balance, Profit & Loss, Balance Sheet, and Trading Account passed 39/39 locally across Chromium, Firefox, and WebKit. On staging, CSV and authenticated print checks passed, but the full Chromium sequence reproducibly caught the P&L Smart Filter hover transition at an intermediate 1.11:1 contrast ratio. Five focused workflow repetitions passed, confirming timing dependence. Shared button foreground/background interpolation has been removed while border, shadow, and movement transitions remain; the focused Angular statement suite passes 82/82 and type checking is clean. Deploy this frontend correction, then rerun the complete 39-check certificate without overrides. |
| Commercial accounting baseline | In progress | The combined sales, purchase, receivables, payables, receipt, payment, register, and accounting-truth backend pack passed 1,062/1,062. Selected staging bank, purchase-to-payment, payables, receivables, and sales-to-receipt scenarios pass in Chromium. All 16 goods/service invoice and credit/debit-note reconciliation scenarios pass in bounded runs. GST symmetry and lookup pagination passed 25/25 across all 12 document surfaces. Expanded AR/AP settlement coverage passed 17/17; payment concurrency/retry/isolation passed 4/4; and taxability preservation passed 15/15 across Chromium, Firefox, and WebKit. Deployed lifecycle and transport recovery cover duplicate actions, rejected writes, authentication expiry, network interruption, and exactly-once import commits. Purchase-register XLSX, CSV, PDF, and browser print passed content and scope verification. The 35-line sales print/PDF case passes, the print-versus-summary modal race is closed, and tablet/mobile preview usability is certified in Chromium, Firefox, and WebKit. Payables direct-export certification now covers 16 report surfaces across Excel, CSV, PDF, and print endpoints and passed on staging in Chromium. Receivables direct-export certification now covers customer outstanding, credit exposure, overdue customers, receivables exceptions, aging summary/invoice, open items, customer ledger, and collections history across Excel, CSV, PDF, and print endpoints and passed on staging in Chromium. Voucher PDF certification now covers cash, bank, journal, payment, and receipt voucher families against staging live rows. Staging passes all nine blocking release-environment checks; SMTP delivery remains a warning. Remaining gates are broader output coverage, accessibility, and infrastructure restore rehearsal. |
| Dataset C oracle | Staging functional certification complete | Manufacturing passed 24/24 on staging. A fresh browser-created asset purchase passed HSN, batch and expiry validation, confirm/post, CWIP posting, linked asset intake, capitalization to the category asset ledger, reversal, unpost, asset removal, and exact ledger-baseline restoration. The affected local backend regression passes 224/224. One purchase invoice created before the corrected posting invariant is still marked Posted without an active source CWIP posting and requires historical data remediation. |
| Dataset C asset report exports | Local correction ready; staging rerun pending | `assets.live.spec.ts` now certifies fixed asset register, depreciation schedule, asset location/custodian, and asset events exports across Excel, CSV, PDF, and print. The staging run exposed a location/custodian Excel 500 caused by `/` in the worksheet title. The shared asset Excel writer now sanitizes invalid worksheet-title characters, and `assets.tests.AssetApiScopeTests.test_report_location_custodian_excel_export_uses_valid_sheet_title --keepdb` passes locally. Deploy backend, then rerun the focused staging export gate. |

## Update Log

| Date | Change | Result |
| --- | --- | --- |
| 16 September 2026 | Added the asset-family direct export certification gate and fixed the first export blocker. | `assets.live.spec.ts` now validates fixed asset register, depreciation schedule, asset location/custodian, and asset events outputs across Excel, CSV, PDF, and print. The first staging Chromium run found a real 500 on location/custodian Excel; local backend regression passes after sanitizing invalid Excel worksheet-title characters. Staging rerun is pending backend deployment. |
| 16 September 2026 | Added the inventory-family direct export certification gate. | `inventory.live.spec.ts` now uses `PLAYWRIGHT_BACKEND_URL` for staging and certifies Stock Summary, Stock Ledger, Stock Aging, Stock Movement, Location Stock, Stock Day Book, Stock Book Summary, Stock Book Detail, Non-Moving Stock, Slow Moving vs Dead Stock, and Reorder Status exports. The new location/book sweep passed 1/1 in 10.7 seconds, and the existing summary/control/aging export checks passed 3/3 in 29.2 seconds on staging Chromium. |
| 16 September 2026 | Added the scenario completeness register to prevent implicit accounting-scope gaps. | Every pilot-significant accounting scenario is now classified as directly covered, covered by linked evidence, partially covered with an explicit launch gate, or intentionally post-pilot. The focused `reports.tests_accounting_truth_matrix` suite passed 12/12 after the update. New scenarios must be added to this register before they can be treated as launch scope. |
| 16 September 2026 | Added the payables-family direct export certification gate. | `payables.live.spec.ts` now validates AP aging, vendor outstanding, vendor ledger, vendor reconciliation, AP compliance aging, MSME overdue, settlement history, note register, upcoming payments, AP GL reconciliation, vendor balance exceptions, AP payment forecast, GRN exceptions, duplicate/anomalous bill detection, and purchase register export URLs. Each surface must return usable Excel, CSV, PDF, and print payloads. The focused staging Chromium run passed 1/1 in 38.1 seconds. |
| 16 September 2026 | Added the voucher-family PDF output certification gate. | `vouchers.live.spec.ts` now discovers live cash, bank, journal, payment, and receipt voucher rows, then verifies each PDF endpoint returns a non-empty `application/pdf` payload with a PDF signature and filename. The focused staging Chromium run passed 1/1 in 7.4 seconds; staging counts showed cash 56, bank 33, journal 32, payment 266, and receipt 27 rows in the certified scope. |
| 16 September 2026 | Hardened and ran the receivables-family export certification gate on staging. | `receivables.live.spec.ts` now uses the configured backend URL for login/RBAC/export requests and parameterizes customer-statement and collections export URLs by live scope. The focused Chromium staging run passed 1/1 in 26.1 seconds, covering customer outstanding, credit exposure, overdue customers, receivables exceptions, aging summary/invoice, open items, customer ledger, and collections history across Excel, CSV, PDF, and print surfaces. |
| 15 September 2026 | Diagnosed a state-dependent P&L accessibility failure during the staging output certificate. | The enriched Axe evidence identified the Smart Filter button at 1.11:1 while its foreground and background hover colors were simultaneously interpolating. The shared button transition now changes contrast-critical colors immediately while retaining border, shadow, and movement animation. Type checking and all 82 focused statement component tests pass; deployment and the final three-browser staging rerun remain required. |
| 15 September 2026 | Added the cross-browser financial statement output and accessibility certificate. | Trial Balance, P&L, Balance Sheet, and Trading Account passed 39/39 across Chromium, Firefox, and WebKit for CSV content, authenticated print content, keyboard export access, overflow, and automated WCAG A/AA checks. The certificate found and fixed an inaccessible horizontally scrollable Trading Account region; the same correction was applied to paired P&L and Balance Sheet tables. Focused Angular tests pass 82/82 and type checking passes. Staging deployment and a no-override rerun remain required. |
| 15 September 2026 | Corrected the shared sales-document utility header across all six invoice and note routes. | Compliance, Find, Transport Details, and Reset now use one stable desktop action rail, uniform sizing, accessible names, and contained tablet/mobile scrolling. The focused Angular suite passes 348/348 with one intentional skip, type checking and the production build pass, and the new `FIN-SALES-HEADER-*` Playwright matrix covers all six routes at 1440x900, 820x1180, and 390x844. Deployment and no-override staging certification remain pending. |
| 15 September 2026 | Corrected and certified sales print-preview usability on tablet and mobile. | `FIN-SAL-PR-033` first reproduced the stage defect in Chromium and WebKit, where the mobile preview retained only 8px. Inspection found GST Validation occupying an implicit third grid row because only toolbar and preview rows were declared. After deployment, the permanent no-override test passed in Chromium, Firefox, and WebKit at 820x1180 and 390x844, confirming dialog containment, useful preview height, horizontal A4 panning, and accessible controls. Supporting evidence remains 362 combined component tests, 14/14 post-diagnosis shared-component tests, and a successful production build. |
| 15 September 2026 | Began commercial print/export certification and fixed sales print modal ownership. | Purchase Register output passed 2/2 with extracted XLSX/CSV/PDF content checks. The independent 35-line multi-page browser/PDF case passes in 1.3 minutes. After deployment, all three formerly blocked goods-print checks passed with browser setup in Chromium: profile switching, standard/thermal downloads, and popup geometry. The confirmation summary no longer obscures Print. |
| 15 September 2026 | Completed deployed commercial failure/recovery certification for lifecycle retries and rapid actions. | Purchase repeated confirm/post passed 12/12 and rapid confirm/post/unpost/cancel passed 24/24 across all six document types. Sales invoice rapid actions passed 8/8, all four sales note types passed 16/16, and payment-voucher lifecycle retries passed 5/5. No duplicate write, unstable status, or UI/API parity defect was found. The only corrections were in Playwright: bounded action probes/stage timeout and a stale confirm-status oracle (`1` to `2`). |
| 15 September 2026 | Executed deployed commercial endpoint failure and retry recovery. | Purchase confirm/post/unpost/cancel rejection preservation passed 5/5 including setup. Sales invoice post/unpost/cancel 500/409 retry passed 4/4 including setup. Sales-note post, unpost, and cancel retries each passed 5/5 including setup across all four note variants. Failed actions preserved the correct pre-action status, surfaced useful messages, remained actionable, and completed exactly once on retry. |
| 15 September 2026 | Completed hardened-stage cross-browser identity/provider recovery checks. | Login HTTP 500 and GST provider failure/retry passed 9/9 including setup across Chromium, Firefox, and WebKit. Expired session plus failed refresh passed 6/6 including setup and consistently exposed the dedicated retry/login recovery path. |
| 15 September 2026 | Closed the commercial HTTP, transport, and purchase-import recovery matrix on staging. | Bulk-print 500/retry, offline download/retry, 403 denial, and failed-refresh redirect passed 4/4 including setup. The new 409/422/429 rejection matrix passed in Chromium, Firefox, and WebKit, and interrupted purchase upload plus timed-out bulk print passed 3/3 including setup in Chromium. Stage-native purchase import passed interrupted validation plus exactly-once commit, lost-response idempotent retry, five rejection statuses with no document creation, and one-failed-refresh redirect in three bounded runs totaling 7/7 including setup. |
| 15 September 2026 | Hardened the staging release environment and completed the cross-browser taxability rerun. | The runtime audit improved from eight blocking failures to zero: debug mode is disabled, the signing key was rotated, hosts are restricted, HTTPS redirect and secure session/CSRF/auth cookies are enabled, and HSTS is active. Firefox tracing identified a Playwright dashboard-readiness race that aborted a successful refresh response before its replacement cookie arrived; the shared dashboard page now waits for a successful `/api/auth/me` bootstrap before navigation. Taxability preservation then passed 15/15 including setup across Chromium, Firefox, and WebKit in 3.4 minutes. SMTP invite/OTP delivery remains the sole environment warning. |
| 15 September 2026 | Expanded Phase 3 commercial document and report reconciliation on staging. | All 16 invoice/note business scenarios pass across bounded Chromium runs, including source document creation, confirm/post, operational registers, party outstanding, Daybook, Ledger Summary, Trial Balance, and party Ledger Books. The full sales-note spec passed 7/7 in 3.7 minutes and the 12-surface GST/lookup matrix passed 25/25. Fixture defects in sales account-head selection, Ship To setup, customer scanning, optional-toast waits, and summary Save recovery were corrected. An oversized mixed process showed browser-runner starvation after 15 tests even though Nginx showed the eventual document requests completing within seconds; launch execution will be split by spec. |
| 15 September 2026 | Expanded Phase 3 settlement and taxability certification on staging. | Three bounded Chromium groups passed 17/17: cash/bank receipts, partial/advance/multi-document AR settlement, settlement policy off, over-settlement block/warn, FIFO/manual allocation, and full/multi/partial/advance-adjusted AP payments. Taxability preservation passed all four surfaces in Chromium and WebKit. Firefox storage-state replay exposed a revoked-session path under insecure cookies, although fresh Firefox login and invoice navigation succeeded with `/api/auth/me` returning 200. The release-environment audit reports eight failed security controls and one SMTP warning; Firefox certification remains blocked until staging configuration is hardened. |
| 15 September 2026 | Added the controlled payment concurrency and isolation staging gate. | `FIN-PUR-CHAIN-005..007` passed 4/4 including authentication in Chromium in 2.4 minutes. Concurrent post protection, terminal retry idempotency, and entity/FY/branch isolation all passed without duplicate settlement or history rows. |
| 15 September 2026 | Started Phase 3 commercial baseline certification. | The backend matrix passed 1,062/1,062. Selected live bank, purchase/payment, payables, receivables, and sales/receipt workflows pass in Chromium. The sales save investigation confirmed correct frontend validation and found a missing Ship To selection in the Playwright fixture; after correction the full sales-to-receipt super-flow passed 2/2 including setup in 49.8 seconds. |
| 15 September 2026 | Completed the deployed isolated destructive year-end close and opening-carry-forward browser certificate. | The final self-cleaning certificate passed 2/2 in Chromium in 1.0 minute and left zero temporary users or entities. Close, duplicate protection, period lock, UI opening generation, source-FY retention, visible UI rollback, rollback dependency, opening purge, close rollback, and restored readiness all passed. Focused component tests remain 25/25. |
| 15 September 2026 | Reran the Core Accounting controls certificate after deploying the Posting Setup reset correction. | The complete staging matrix passed 45/45 across Chromium, Firefox, and WebKit in 5.2 minutes. The reset baseline, WebKit navigation, responsive layouts, failure recovery, confirmation safeguards, keyboard access, and automated WCAG A/AA checks all passed. |
| 15 September 2026 | Started the Core Accounting and Year-End Close staging gate. | Backend close invariants passed 37/37. The staging controls matrix passed 40/45 and exposed a deterministic Posting Setup reset defect across Chromium, Firefox, and WebKit; two additional WebKit bootstrap timeouts passed 3/3 after raising the navigation allowance to 30 seconds. The reset correction passes 20/20 component tests and a production build, with deployment and the final 45-test rerun pending. |
| 15 September 2026 | Reran Dataset B inventory report certification after deploying the Stock Ledger deficit-ordering correction. | The full staging matrix passed 24/24 across Chromium, Firefox, and WebKit in 4.3 minutes. The former Product X1 mismatch is resolved at 107 units, and all inventory report scope, drilldown, and numeric reconciliation checks pass. |
| 15 September 2026 | Started Dataset B staging certification with cross-browser inventory reconciliation and controlled concurrency probes. | The report run passed 20/24 and consistently exposed a real 10-unit Stock Summary versus Stock Ledger mismatch. The ledger now carries negative-before-receipt deficits by product/location/batch across FIFO, LIFO, moving average, weighted average, and latest cost, and custom-period opening state no longer mutates with period activity. Local inventory reports pass 28/28, Dataset B passes 6/6, Django check is clean, Firefox harness rerun passes 2/2, and staging concurrency passes 3/3 with cleanup. Deployment and the final 24/24 report rerun remain. |
| 15 September 2026 | Reran the self-cleaning Dataset A opening-balance source gate after deploying the code-series correction. | `FIN-ACCT-OPEN-001` passed 2/2 on staging in 34.9 seconds. The test reconciled the two 100,000.00 openings through Trial Balance, Balance Sheet, Daybook, and Ledger Book, then removed both temporary accounts. |
| 15 September 2026 | Ran the unmocked Dataset A live financial report matrix on staging across all three browser engines. | The final hardened run passed 24/24. An initial Firefox workspace-recovery failure was traced to browser session context rather than report logic; the suite now explicitly restores entity, FY, branch, RBAC, and menu context before each check. |
| 15 September 2026 | Started the self-cleaning Dataset A opening-balance staging source gate. | Negative-opening validation passed, but valid account creation exposed a stale code-series cursor colliding with an existing entity ledger. The allocator now skips occupied codes under the series row lock, and the complete local `financial.tests` suite passes 106/106. Deployment and one staging rerun remain. |
| 15 September 2026 | Retested the deployed CWIP capitalization correction and added a fresh browser-based purchase-to-asset lifecycle certificate. | Deployed capitalization, reversal, depreciation posting, and depreciation cancellation passed. The final fresh end-to-end scenario passed 2/2 including setup in 1.5 minutes, restored both CWIP and final asset ledger balances to their exact pre-test values, removed the linked intake asset, and cancelled its source QA invoice. The old purchase-linked fixture remains a historical data anomaly rather than a failure of newly posted transactions. |
| 15 September 2026 | Ran Dataset C manufacturing and asset certification on staging after deployment. | Manufacturing passed 24/24 with report API p95 between 324 ms and 409 ms. Asset testing found that purchase-intake capitalization could debit and credit CWIP while marking the asset Active. The staging mutation was reversed, the backend now transfers CWIP into the category asset ledger and restores CWIP on reversal, and the affected local regression passes 224/224. |
| 14 September 2026 | Defined Dataset A events, journal expectations, closing balances, report assertions, and required variants. | Phase 0 now has a fixed first accounting oracle. |
| 14 September 2026 | Ran the focused posting, account-master, financial-book, opening, and year-end close baseline. | 250/250 tests passed; no Django system-check issue. Cross-report Dataset A automation remains the next task. |
| 14 September 2026 | Corrected the Dataset A balance-sheet oracle before automation. | Input GST remains an asset and output GST a liability for presentation; both sides are 107,800.00 and net GST remains 1,080.00 payable. |
| 14 September 2026 | Added and executed the isolated Dataset A cross-report integration test. | Dataset A passed alone and in the combined 251-test accounting suite; daybook, ledgers, TB, P&L, and balance sheet reconcile. |
| 14 September 2026 | Added lifecycle filtering and real AR/AP settlement coverage to Dataset A. | The isolated 3-test oracle and combined 253-test accounting pack passed; receivable 11,800.00 and payable 4,720.00 both reconcile to zero after their dated allocations. |
| 14 September 2026 | Added Dataset A GST register-to-ledger proof and fixed a GSTR-1 query failure caused by annotating over the existing `posting_date` model field. | Dataset A passed 4/4, dedicated GSTR-1 passed 67/67, and the combined accounting/GSTR-1 pack passed 321/321. |
| 14 September 2026 | Added the Dataset A Playwright presentation contract and reran the seeded financial browser regression. | The accounting contract passed 6/6 across Chromium, Firefox, and WebKit; the existing Chromium seeded suite passed 13/13. Live source-document creation and staging reconciliation remain pending. |
| 14 September 2026 | Exercised the first unmocked source-document browser chain for cash, bank, journal, sales/receipt, and purchase/payment. | All five business workflows produced passing evidence, including an isolated end-to-end sales settlement and rendered Open Items proof. The combined sequential run remains blocked by local report/navigation latency, so Phase 0 is not yet signed off. |
| 14 September 2026 | Stabilized repeated report navigation and removed the redundant post-settlement Open Items reload. | The decisive sequential browser launch selection passed 6/6 in 5.8 minutes; the prior local performance blocker is closed. |
| 14 September 2026 | Added named-account browser scenarios for capital introduction, expense accrual/reversal, and bank-to-cash contra. | The combined event run passed 4/4 in 1.9 minutes. Strict opening-balance master/import certification and staging execution remain open. |
| 14 September 2026 | Certified strict account-opening behavior and corrected Ledger Book branch scoping for entity-level opening postings. | Financial-books tests passed 82/82 and the live opening browser certificate passed 2/2. Daybook exclusion is intentional; Trial Balance, Balance Sheet, and both opening Ledger Books reconcile at 100,000.00 per side. Staging execution remains open. |
| 14 September 2026 | Defined and automated the Dataset B trading baseline with fixed purchase, return, freight, sale, sales-return, receipt, payment, GST, and FIFO expectations. | The source-backed oracle reconciles 15 closing units at 1,800.00, profit 4,800.00, net GST payable 756.00, bank 103,756.00, zero AR/AP ledgers, and a 107,500.00 balanced Balance Sheet. The combined accounting, register, GSTR-1, and books regression passed 185/185. |
| 14 September 2026 | Automated Dataset B Variant 1 for capitalized landed cost and multiple purchase-cost layers. | Purchase posting remains balanced while landed cost flows into inventory. FIFO closes 30 units at 5,400.00 with profit 15,400.00; moving average closes at 4,000.00 with profit 14,000.00. Product-filtered inflow valuation was corrected to use the same scope as opening and closing stock; the focused regression passed 199/199. |
| 14 September 2026 | Automated Dataset B Variant 2 for discounts, tax-inclusive pricing, composite CESS, and round-off. | Purchase and sales calculations and postings reconcile to the fixed 1,090.00 line oracle. Inventory, tax controls, Trial Balance, Trading Account, and P&L pass together; the expanded focused regression passed 249/249. |
| 14 September 2026 | Automated Dataset B Variant 3 for exact batch/location stock, partial returns, and negative-stock policy. | Fixed product-level cost-layer pooling that allowed Location B issues to consume Location A costs. All five valuation methods now isolate inventory identity; location values 7,500.00 and 4,800.00 reconcile to entity value 12,300.00, and the expanded regression passed 569/569. |
| 14 September 2026 | Automated Dataset B Variant 4 for split settlements, advances, and AR/AP reconciliation. | Customer exposure 3,500.00 and vendor exposure 3,000.00 reconcile to their control ledgers after split cash allocations and partial advance use. One-cent tolerant inputs are now capped to exact balances, larger excesses are blocked without mutation, the settlement/report pack passed 293/293, and the expanded regression passed 570/570. |
| 14 September 2026 | Automated Dataset B Variant 5 for inter-state IGST and exempt, nil-rated, and non-GST supplies. | Purchase/sales registers, GSTR-1 taxability buckets, GSTR-3B sections, GST control ledgers, FIFO stock, Trial Balance, Trading Account, and P&L reconcile to fixed values; all non-taxable streams carry zero GST. The statutory/reporting pack passed 186/186 and the expanded regression passed 571/571. |
| 14 September 2026 | Completed Dataset B Variant 6 for lifecycle retries and competing-client protection. | Purchase and sales lifecycle actions now lock the source row, reject stale versions with HTTP 409, preserve successful terminal retries, and avoid duplicate reversal batches. The backend matrix passed 1,011/1,011, the Angular lifecycle pack passed 822 with one existing skip, and the development build passed. |
