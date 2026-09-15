# Accounting Truth Matrix

Status: Phase 0 baseline in progress

Last updated: 14 September 2026

Execution plan: [Accounting-First Product Completion Plan](../product/accounting-first-completion-plan-2026-09-14.md)

## Purpose

This register is the accounting oracle for source-to-report certification. Amounts below are fixed expected results, not values copied from application reports after execution.

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

Status: Baseline plus landed-cost/layered-valuation Variant 1, discount/tax/CESS Variant 2, batch/location/partial-return Variant 3, settlement/advance Variant 4, IGST/taxability Variant 5, and lifecycle/concurrency Variant 6 automated locally.

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

Status: Local numeric oracle complete; staging certification pending.

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
| Dataset A staging run across three browsers | Pending | Requires deployed backend/frontend revision |
| Dataset B fixed oracle | Complete locally | `TradingEntityAccountingTruthMatrixTests` proves posted source invoices/credit notes, FIFO quantity/value, Daybook, Ledger Summary, Trial Balance, Trading Account, P&L, Balance Sheet, GST registers/control ledgers, and zero party-ledger balances after settlement. |
| Dataset B Variant 1 | Complete locally | Capitalized header expenses balance the purchase journal and increase inventory unit cost; two landed-cost layers reconcile closing stock, COGS, and gross profit under FIFO and moving-average valuation. The focused accounting, register, GSTR-1, books, and purchase-adapter pack passed 199/199. |
| Dataset B Variant 2 | Complete locally | Discount-before-tax ordering, tax-inclusive back-calculation, composite CESS, positive purchase round-off, negative sales round-off, inventory cost, Trial Balance, Trading Account, and P&L reconcile to fixed values. The expanded focused regression passed 249/249. |
| Dataset B Variant 3 | Complete locally | Two locations and two batches prove exact-pool valuation, partial purchase/sales returns, entity-to-location reconciliation, no cross-location stock borrowing, strict shortage blocking, controlled negative-stock behavior, and truthful negative quantity reporting. The expanded regression passed 569/569. |
| Dataset B Variant 4 | Complete locally | Split receipts/payments, residual customer/vendor advances, partial advance applications, over-allocation rollback, AR/AP reports, party control ledgers, Trial Balance, and Daybook reconcile. The settlement/report pack passed 293/293 and the expanded purchase, sales, inventory, and accounting regression passed 570/570. |
| Dataset B Variant 5 | Complete locally | Inter-state purchases and sales plus exempt, nil-rated, and non-GST streams reconcile across operational registers, GSTR-1, GSTR-3B, GST control ledgers, inventory, Trial Balance, Trading Account, and P&L. The statutory/reporting pack passed 186/186 and the expanded purchase, sales, inventory, and accounting regression passed 571/571. |
| Dataset B Variant 6 | Complete locally | Purchase and sales lifecycle transitions use row locks and optional server-version checks; stale clients receive HTTP 409, terminal retries remain successful, and repeated unpost/reverse does not create duplicate reversal batches. Backend passed 1,011/1,011; focused Angular lifecycle coverage passed 822 with one existing skip; the frontend development build passed. |
| Dataset B remaining variants | Complete locally | All six planned trading-entity variants now have local automated evidence. Staging repetition remains part of the Phase 0 gate. |
| Dataset C oracle | Complete locally | Manufacturing, finished-goods COGS, asset depreciation, statements, reversal, and closed-year controls pass fixed numeric oracles. Staging repetition remains open. |

## Update Log

| Date | Change | Result |
| --- | --- | --- |
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
