# Finacc India Statutory Compliance E2E Matrix

Purpose: define end-to-end statutory test cases for current Finacc India compliance flows across purchase, sales, withholding, reporting, period controls, and ledger accuracy.

Scope notes:
- This matrix follows current product behavior and existing service boundaries.
- Backend remains the source of truth for tax, posting, statutory controls, and period locks.
- Reverse charge on purchase remains header-level in the current model.
- Multi-GSTIN entity behavior and future-dated purchase policy remain separate open gaps and are not restated as green scenarios here.

## Coverage Tracker

Status legend:
- `Automated`: proven by existing backend, API, posting, report, or reconciliation tests.
- `Partial`: meaningful automated evidence exists, but not yet as one clean end-to-end statutory scenario.
- `Gap`: still needs explicit automation or product clarification before it should be treated as covered.

| Test ID | Status | Current evidence |
| --- | --- | --- |
| `PUR-GST-001` | Automated | Purchase service and e2e validation coverage, purchase register, and GSTR-3B suites |
| `PUR-GST-002` | Automated | Purchase service and e2e interstate handling, purchase register, and GSTR-3B suites |
| `PUR-GST-003` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/tests_purchase_register.py`, `reports/gstr3b/tests/test_gstr3b_summary.py`, `gst_reconciliation/tests.py` |
| `PUR-RCM-001` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` |
| `PUR-ITC-001` | Automated | `purchase/tests.py`, `reports/tests_purchase_register.py`, `reports/gstr3b/tests/test_gstr3b_summary.py`, `gst_reconciliation/tests.py` |
| `PUR-GST-004` | Automated | `purchase/tests_e2e_api.py` plus purchase reporting suites |
| `PUR-IMP-001` | Automated | `purchase/tests.py`, `reports/gstr3b/tests/test_gstr3b_summary.py`, `gst_reconciliation/tests.py` |
| `PUR-IMP-002` | Automated | `purchase/tests.py`, purchase RCM reporting coverage |
| `PUR-ITC-002` | Automated | `purchase/tests_e2e_api.py`, `purchase/tests_itc_policy.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` |
| `PUR-TDS-001` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py`, purchase statutory service tests |
| `PUR-TDS-002` | Automated | `purchase/tests.py`, `withholding/tests.py` |
| `PUR-CTRL-001` | Automated | Purchase posting and static-account failure coverage in `purchase/tests.py` |
| `SAL-GST-001` | Automated | `sales/tests_e2e_api.py`, `sales/tests_invoice_contract_alignment.py`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_sales_register.py` |
| `SAL-GST-002` | Automated | `sales/tests_e2e_api.py`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_sales_register.py` |
| `SAL-GST-003` | Automated | `sales/tests_e2e_api.py`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_sales_register.py` |
| `SAL-TCS-001` | Automated | `sales/tests.py`, `receipts/tests.py`, `withholding/tests.py` |
| `SAL-TCS-002` | Automated | `sales/tests.py`, `withholding/tests.py` |
| `SAL-CTRL-001` | Automated | `sales/tests.py` |
| `PER-PUR-001` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py` |
| `PER-PUR-002` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/tests_purchase_register.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` |
| `PER-SAL-001` | Automated | `sales/tests.py`, `sales/tests_e2e_api.py` |
| `RPT-GST-001` | Automated | `reports/gstr3b/tests/test_gstr3b_summary.py`, purchase correction-flow tests |
| `RPT-GST-002` | Automated | `reports/gstr1/tests/test_gstr1_report.py` |
| `RPT-GST-003` | Automated | `gst_reconciliation/tests.py`, `reports/tests_gst_reconciliation.py`, purchase reconciliation tests |
| `RPT-TCS-001` | Automated | `withholding/tests.py` |
| `RPT-WHT-001` | Automated | `withholding/tests.py`, purchase statutory readiness tests |
| `LEDGER-001` | Automated | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `sales/tests_e2e_api.py`, posting adapter tests |
| `LEDGER-002` | Automated | `reports/tests_purchase_register.py`, `reports/tests_sales_register.py`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_books.py`, `purchase/tests_e2e_api.py` |

## Coverage Summary

- `Automated`: 28
- `Partial`: 0
- `Gap`: 0

## Next Automation Priorities

1. Keep the tracker green while extending statutory depth only where we want stronger scenario granularity, not because of known uncovered flows.

## Purchase GST Compliance Map

| Case | Scenario | Mapped test coverage | Status | Core outcome covered |
| --- | --- | --- | --- | --- |
| `A01` | Registered vendor valid GSTIN same-state purchase | `PUR-GST-001` | Automated | CGST or SGST, input GST, vendor payable, GSTR-3B, purchase register |
| `A02` | Registered vendor valid GSTIN interstate purchase | `PUR-GST-002` | Automated | IGST, input GST, vendor payable, GSTR-3B, purchase register |
| `A03` | Registered vendor without GSTIN must block posting | `PUR-GST-001` plus purchase vendor validation tests | Automated | Validation block before save or post |
| `A04` | Registered vendor inactive or cancelled GSTIN should warn or block as per policy | `PUR-GST-001` plus vendor compliance policy tests | Automated | Policy-driven warning or hard stop |
| `A05` | URD vendor no GST no RCM | `PUR-GST-003` | Automated | No supplier GST, no normal ITC, excluded from normal reconciliation |
| `A06` | URD vendor with GST amount must block | `PUR-GST-003` plus bulk-import and validation tests | Automated | GST charging blocked for URD non-RCM |
| `A07` | URD vendor with RCM | `PUR-RCM-001` | Automated | Header-level RCM liability, gated ITC, GSTR-3B RCM bucket |
| `A08` | Composition vendor purchase blocks ITC | `PUR-ITC-001` | Automated | ITC blocked, excluded from normal 2B claim flow |
| `A09` | SEZ purchase with tax | `PUR-GST-004` | Automated | Explicit SEZ taxed treatment, interstate GST path |
| `A10` | SEZ purchase without tax | `PUR-GST-004` | Automated | Explicit SEZ non-taxed treatment, no domestic fallback |
| `A11` | Import goods purchase | `PUR-IMP-001` | Automated | Import treatment separated from domestic supplier GST and normal reconciliation |
| `A12` | Import service with RCM | `PUR-IMP-002` | Automated | RCM required, import-service liability path |
| `A13` | Exempt purchase | `PUR-GST-004` taxability coverage and purchase reporting suites | Automated | No claimable GST, correct statutory classification |
| `A14` | Nil-rated purchase | `PUR-GST-004` taxability coverage and purchase reporting suites | Automated | No claimable GST, correct statutory classification |
| `A15` | Non-GST purchase | `PUR-GST-004` taxability coverage and purchase reporting suites | Automated | No GST, excluded from normal ITC logic |
| `A16` | Purchase credit note | `PER-PUR-002`, `RPT-GST-001`, purchase note and posting tests | Automated | Separate correction posting, current-period GST or ITC impact |
| `A17` | Purchase debit note | `PER-PUR-002` and purchase note lifecycle tests | Automated | Separate correction posting, positive value adjustment path |
| `A18` | Purchase return | `PER-PUR-002` plus quantity-return inventory safety tests | Automated | Inventory-safe return flow, separate correction document |
| `A19` | Filed-period purchase correction | `PER-PUR-002` | Automated | Original unchanged, current-period correction, report impact in correction period |
| `A20` | Locked-period purchase edit or unpost or cancel behavior | `PER-PUR-001`, `PER-PUR-002` | Automated | Edit blocked, unpost blocked, cancel routed to correction-note flow |

Expected outcome alignment for `A01` to `A20`:
- Correct `CGST` or `SGST` or `IGST`: covered through `PUR-GST-001`, `PUR-GST-002`, `PUR-RCM-001`, `PUR-GST-004`, `PUR-IMP-001`, and `PUR-IMP-002`
- Correct GST ledgers: covered through purchase posting tests, correction-note polarity tests, and grouped statutory regression
- Correct vendor payable: covered through purchase posting, AP open-item, cancel, correction-note, and payment-flow tests
- Correct `GSTR-3B`: covered through `RPT-GST-001` and `reports/gstr3b/tests/test_gstr3b_summary.py`
- Correct purchase register: covered through `reports/tests_purchase_register.py`
- Correct GST reconciliation inclusion or exclusion: covered through `RPT-GST-003` and `gst_reconciliation/tests.py`

## Purchase ITC Compliance Map

| Case | Scenario | Mapped test coverage | Status | Core outcome covered |
| --- | --- | --- | --- | --- |
| `B01` | Fully eligible ITC | `PUR-ITC-002`, `RPT-GST-001` | Automated | Eligible taxable purchase can be matched and claimed into normal ITC buckets |
| `B02` | Ineligible ITC | `PUR-ITC-002`, `RPT-GST-001` | Automated | Ineligible or forced-non-eligible purchase stays out of claimable ITC and contributes to reversed or blocked treatment |
| `B03` | Partially eligible ITC | `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py`, tax-summary split in `purchase_invoice_service.py` | Automated | Mixed line-level eligible and ineligible tax is captured in purchase tax summaries and now flows into `GSTR-3B` available vs reversed ITC tax buckets |
| `B04` | Blocked ITC category | `PUR-ITC-002`, purchase ITC action e2e coverage | Automated | Block action flips claim status and keeps blocked tax out of normal claimed ITC |
| `B05` | Capital goods ITC | Asset-purchase, asset-intake, asset-line ITC claim coverage in `purchase/tests.py` and `purchase/tests_e2e_api.py`, plus asset purchase contribution to `GSTR-3B` normal ITC bucket in `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Current model supports capital-goods purchase plus normal ITC workflow, and reports that ITC in the standard eligible ITC bucket rather than a separate capital-goods bucket |
| `B06` | RCM ITC pending before payment | `PUR-ITC-002`, `purchase/tests_itc_policy.py` | Automated | RCM ITC claim is blocked until reverse-charge payment tracking exists |
| `B07` | RCM ITC eligible after payment | `purchase/tests_itc_policy.py`, `purchase/tests_e2e_api.py`, posted payment-voucher AP settlement trail in purchase ITC action service | Automated | RCM ITC stays blocked before payment and becomes claimable once any posted payment voucher settles that invoice |
| `B08` | 2B matched invoice | `PUR-ITC-002`, purchase GSTR-2B action tests | Automated | Matched status can be set and used for ITC claim gating |
| `B09` | 2B unmatched invoice | `purchase/tests_itc_policy.py`, purchase GSTR-2B action tests | Automated | Non-allowed 2B states can block claim under policy-driven gates |
| `B10` | 2B partial match | `purchase/tests_itc_policy.py`, `purchase/tests_e2e_api.py`, import and match services persist `PARTIAL` | Automated | Partial-match status can be set and still pass ITC claim gating when policy explicitly allows it |
| `B11` | ITC hold | `PUR-ITC-002` block action | Automated | ITC can be put on hold through block workflow with visible blocked status |
| `B12` | ITC release | `PUR-ITC-002` unblock action | Automated | Held ITC can be restored to pending state through unblock workflow |
| `B13` | ITC reversal through credit note | `PUR-ITC-002`, `RPT-GST-001` | Automated | Purchase credit note reverses prior input-tax impact in current reporting period |
| `B14` | ITC reversal in current period for filed-period invoice | `PER-PUR-002`, `RPT-GST-001` | Automated | Filed-period original stays unchanged and ITC adjustment posts into current-period correction bucket |
| `B15` | Composition vendor ITC blocked | `PUR-ITC-001`, `RPT-GST-003` | Automated | Composition purchase cannot flow into normal claimable ITC or normal 2B reconciliation |
| `B16` | URD non-RCM ITC blocked | `PUR-GST-003`, `RPT-GST-003` | Automated | URD non-RCM purchase stays non-claimable and excluded from normal reconciliation |
| `B17` | Import ITC handling | `PUR-IMP-001`, `PUR-IMP-002`, `RPT-GST-001`, `RPT-GST-003` | Automated | Import goods stay out of domestic normal ITC flow; import service follows RCM-gated ITC path |
| `B18` | Rule 42 or 43 placeholder or unsupported scenario should be documented | `purchase-findings-and-improvements.md` gap notes | Gap | No explicit Rule 42 or Rule 43 engine or automation is present; this remains documented as unsupported scope |

Expected outcome alignment for `B01` to `B18`:
- ITC status correct: covered through ITC block, unblock, claim, reverse, and 2B-status action tests in `purchase/tests_e2e_api.py` and `purchase/tests_itc_policy.py`
- ITC claim bucket correct: covered through `reports/gstr3b/tests/test_gstr3b_summary.py` for eligible, blocked, reversed, and reverse-charge cases
- Blocked or ineligible ITC not claimed: covered through `PUR-ITC-002`, composition coverage, URD non-RCM coverage, and import-goods handling
- `GSTR-3B` ITC values correct: covered through `RPT-GST-001` grouped summary assertions
- 2B reconciliation behavior correct: covered through `gst_reconciliation/tests.py`, purchase GSTR-2B batch tests, and purchase action gate tests
- Filed-period ITC adjustments go to current period: covered through `PER-PUR-002` plus current-period correction assertions in `reports/gstr3b/tests/test_gstr3b_summary.py`

## Purchase RCM Compliance Map

| Case | Scenario | Mapped test coverage | Status | Core outcome covered |
| --- | --- | --- | --- | --- |
| `C01` | URD RCM same-state | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Same-state URD RCM now has explicit named coverage for zero supplier GST, derived `CGST` plus `SGST` in tax summary, posting liability, and `GSTR-3B` reverse-charge reporting |
| `C02` | URD RCM interstate | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Interstate URD RCM now has explicit named coverage for zero supplier GST, derived `IGST` in tax summary, posting liability, and `GSTR-3B` reverse-charge reporting |
| `C03` | GTA service RCM | `purchase/tests_e2e_api.py`, `purchase/tests.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | GTA-style service invoices now have explicit named RCM coverage through the generic service reverse-charge path, tax summary derivation, and reverse-charge reporting |
| `C04` | Legal service RCM | `purchase/tests_e2e_api.py`, `purchase/tests.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Legal-service-style invoices now have explicit named RCM coverage through the generic service reverse-charge path, tax summary derivation, and reverse-charge reporting |
| `C05` | Import of service RCM | `PUR-IMP-002`, `purchase/tests.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Import service requires RCM, creates reverse-charge statutory treatment, and stays out of normal domestic supplier GST flow |
| `C06` | RCM invoice without tax rate should block | `PUR-RCM-001`, purchase validation tests | Automated | Header-level RCM requires tax rate and blocks incomplete payloads |
| `C07` | RCM invoice without place of supply should block | `PUR-RCM-001`, purchase validation tests | Automated | Header-level RCM requires place of supply and blocks incomplete payloads |
| `C08` | RCM liability created on posting | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Original RCM posting is now explicitly proven to derive liability from purchase tax summaries even when supplier GST on the saved invoice is zero |
| `C09` | RCM payment clears payable | `purchase/tests_e2e_api.py`, `purchase/tests_itc_policy.py`, AP settlement service coverage | Automated | Posted invoice payment is explicitly proven to settle the payable open item to zero outstanding and unlock RCM ITC under the current payment-based release policy |
| `C10` | RCM ITC allowed after payment | `purchase/tests_itc_policy.py`, `purchase/tests_e2e_api.py`, `purchase/services/purchase_invoice_actions.py` | Automated | RCM ITC is blocked before payment and becomes claimable after any posted payment on that invoice |
| `C11` | RCM credit note adjustment | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Reverse-charge credit note preserves RCM context, reverses liability or input polarity correctly, and affects current-period reporting |
| `C12` | RCM filed-period correction | `PER-PUR-002`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Filed-period RCM originals remain unchanged and current-period correction documents carry the statutory adjustment |
| `C13` | RCM excluded from normal supplier GST or 2B flow | `PUR-RCM-001`, `RPT-GST-003`, `gst_reconciliation/tests.py` | Automated | Reverse-charge inward supplies remain outside the normal supplier GST and domestic 2B match flow |

Expected outcome alignment for `C01` to `C13`:
- RCM output liability created: covered through explicit same-state and interstate RCM posting tests, reverse-charge credit-note polarity tests, and `GSTR-3B` reverse-charge bucket assertions
- RCM input tracked separately: covered through purchase ITC action flow, reverse-charge gating, and reverse-charge correction tests
- ITC not claimable before payment: covered through `purchase/tests_itc_policy.py` and purchase ITC lifecycle e2e tests
- `GSTR-3B` RCM liability correct: covered through `reports/gstr3b/tests/test_gstr3b_summary.py`
- Current-period correction works: covered through filed-period purchase correction and reverse-charge credit-note current-period tests

## Purchase GST / ITC / RCM

### Test ID: `PUR-GST-001`
- Module: Purchase
- Scenario: Registered GST vendor same-state taxable purchase
- Input data: Regular vendor with valid GSTIN, same-state place of supply, taxable goods line, GST rate 18%, posted invoice in open period
- Expected validation: GSTIN required and accepted, invoice number and supplier invoice date mandatory, CGST and SGST derived instead of IGST
- Expected accounting entry: Inventory or expense debit, input CGST debit, input SGST debit, vendor payable credit
- Expected statutory impact: Eligible input GST captured as normal ITC, no RCM
- Expected report impact: Purchase register, GST input register, and GSTR-3B normal ITC buckets include the invoice
- Expected API behavior: Create, confirm, and post endpoints succeed and return backend-computed tax totals
- Expected UI behavior: GST treatment and totals display as backend-derived, save and post actions succeed
- Negative checks: GSTIN missing, invalid, or tax split overridden by client must be blocked or ignored by backend

### Test ID: `PUR-GST-002`
- Module: Purchase
- Scenario: Registered GST vendor interstate taxable purchase
- Input data: Regular vendor with valid GSTIN, interstate place of supply, taxable goods or service line, GST rate 18%
- Expected validation: GSTIN required and accepted, IGST path applied, no CGST or SGST on saved totals
- Expected accounting entry: Inventory or expense debit, input IGST debit, vendor payable credit
- Expected statutory impact: Eligible IGST ITC captured as normal ITC
- Expected report impact: Purchase register and GSTR-3B reflect IGST-only input tax
- Expected API behavior: Backend persists IGST totals and rejects inconsistent client-side tax breakup
- Expected UI behavior: Interstate regime visible after recalculation, read-only totals match saved document
- Negative checks: Same-state tax breakup on an interstate document must be rejected or recomputed

### Test ID: `PUR-GST-003`
- Module: Purchase
- Scenario: Unregistered vendor purchase without GST and without RCM
- Input data: Vendor without GSTIN, URD treatment, taxable line, reverse charge disabled
- Expected validation: GSTIN remains blank, supplier GST amounts must be zero, normal ITC not allowed
- Expected accounting entry: Inventory or expense debit, vendor payable credit, no input GST ledger line
- Expected statutory impact: No supplier GST claim and no RCM liability
- Expected report impact: Purchase register includes URD purchase, GSTR-3B normal ITC buckets exclude it, GST reconciliation excludes it from 2B matching
- Expected API behavior: Backend suppresses supplier GST and ITC even if client sends GST values
- Expected UI behavior: GST fields recalculate to zero and ITC state is shown as non-claimable
- Negative checks: URD invoice with supplier GST amounts or manual ITC claim must be blocked

### Test ID: `PUR-RCM-001`
- Module: Purchase
- Scenario: Unregistered vendor purchase with header-level reverse charge
- Input data: Vendor without GSTIN, reverse charge enabled at header, HSN or SAC, tax rate, place of supply, open period
- Expected validation: RCM requires tax rate and place of supply, supplier GST remains zero, ITC not claimable before payment gate
- Expected accounting entry: Base purchase debit, vendor payable credit, RCM liability credit, deferred or gated input tax handling per service policy
- Expected statutory impact: Reverse-charge liability created; ITC remains pending until payment condition is satisfied
- Expected report impact: GSTR-3B reverse-charge liability bucket populated; normal supplier ITC bucket excluded
- Expected API behavior: Backend accepts valid header-level RCM payload and computes zero supplier GST with RCM summary
- Expected UI behavior: RCM flag is visible, tax values are backend driven, ITC status shows pending or gated state
- Negative checks: Missing place of supply, missing tax rate, or supplier GST on RCM document must be blocked

### Test ID: `PUR-ITC-001`
- Module: Purchase
- Scenario: Composition vendor purchase
- Input data: Vendor compliance profile marked composition, taxable lines, reverse charge disabled
- Expected validation: Composition treatment drives invoice behavior, supplier GST is not treated as claimable ITC
- Expected accounting entry: Base purchase debit, vendor payable credit, no normal claimable input GST ledger effect
- Expected statutory impact: ITC blocked for normal composition purchase
- Expected report impact: Purchase register reflects composition treatment; GSTR-3B normal ITC bucket excludes claim; GST reconciliation excludes normal 2B claim behavior
- Expected API behavior: Backend blocks or neutralizes claimable ITC on composition purchase regardless of client payload
- Expected UI behavior: Composition vendor status is visible and ITC controls resolve to blocked or read-only
- Negative checks: Manual claim of supplier GST ITC on composition purchase must fail

### Test ID: `PUR-GST-004`
- Module: Purchase
- Scenario: SEZ purchase with tax and without tax
- Input data: Vendor marked SEZ, one taxable SEZ invoice with IGST, one non-taxed SEZ invoice with explicit SEZ treatment
- Expected validation: SEZ treatment drives INTER regime behavior explicitly and does not fall back to normal domestic purchase logic
- Expected accounting entry: With-tax case posts input IGST if eligible; without-tax case posts base cost only
- Expected statutory impact: SEZ taxable and non-taxed variants remain distinct for GST treatment and ITC eligibility
- Expected report impact: Purchase register and GSTR-3B classify SEZ purchases into the supported interstate or import-style buckets as configured
- Expected API behavior: Backend persists explicit tax treatment and computes correct zero-tax or IGST totals
- Expected UI behavior: Tax treatment remains explicit and read-only totals match backend regime determination
- Negative checks: Domestic same-state CGST or SGST treatment must not be allowed for SEZ path

### Test ID: `PUR-IMP-001`
- Module: Purchase
- Scenario: Import of goods purchase
- Input data: Import goods tax treatment, foreign or import vendor, IGST or import tax structure, open period
- Expected validation: Import goods must not be treated as a normal domestic supplier-GST purchase
- Expected accounting entry: Inventory or cost debit, import-related tax handling separate from normal domestic supplier GST, vendor or clearing account credit
- Expected statutory impact: Import path stays out of normal domestic supplier ITC logic
- Expected report impact: GSTR-3B import-related bucket used where supported; GST reconciliation excludes normal 2B matching
- Expected API behavior: Backend accepts import treatment and excludes the document from domestic supplier-GST matching assumptions
- Expected UI behavior: Import treatment shown explicitly; normal domestic GST cues should not appear
- Negative checks: Import goods must not flow into domestic normal ITC or domestic reconciliation paths

### Test ID: `PUR-IMP-002`
- Module: Purchase
- Scenario: Import of services with reverse charge
- Input data: Import service treatment, service line, reverse charge enabled, tax rate and place of supply present
- Expected validation: Import service requires reverse charge handling and should not behave like normal domestic purchase
- Expected accounting entry: Expense debit, vendor payable credit, reverse-charge liability credit, gated ITC handling
- Expected statutory impact: Import of service liability appears in reverse-charge bucket and ITC follows payment-gate policy
- Expected report impact: GSTR-3B reverse-charge and import buckets reflect the invoice; normal 2B match flow excludes it unless explicit support exists
- Expected API behavior: Backend rejects incomplete RCM import payload and computes statutory flags centrally
- Expected UI behavior: RCM and import treatment shown together with backend-authoritative totals
- Negative checks: Supplier GST amounts, missing place of supply, or missing tax rate must fail

### Test ID: `PUR-ITC-002`
- Module: Purchase
- Scenario: ITC claim gating for matched, blocked, and reversed inputs
- Input data: One eligible registered purchase, one blocked ITC purchase, one RCM purchase before payment, and one purchase credit note reversing input tax
- Expected validation: Eligible ITC goes to input ledgers, blocked ITC remains non-claimable, pre-payment RCM ITC stays gated, credit note reverses prior ITC
- Expected accounting entry: Eligible invoice debits input tax ledger; blocked credit stays in base cost or blocked path; credit note reverses input tax polarity
- Expected statutory impact: ITC status transitions remain visible and current-period adjustments reverse ITC when correction note posts
- Expected report impact: GSTR-3B normal ITC buckets, reverse-charge bucket, and current-period adjustments reconcile to document set
- Expected API behavior: Status-changing actions and posting flow return backend-derived ITC state
- Expected UI behavior: ITC status, block reason, and claimability state display consistently from backend response
- Negative checks: Client-side attempt to force claimable ITC on blocked or pre-payment RCM document must not persist

## Purchase TDS / Statutory Controls

### Test ID: `PUR-TDS-001`
- Module: Purchase
- Scenario: TDS-applicable purchase at booking
- Input data: Vendor mapped to applicable TDS section, taxable service invoice, threshold crossed, PAN available
- Expected validation: Section applicability, threshold, and rate resolved by withholding service
- Expected accounting entry: Expense debit, input tax debits if eligible, vendor payable credit net of deducted TDS when booking-basis deduction applies, TDS payable credit
- Expected statutory impact: TDS exposure created with resolved section and rate snapshot
- Expected report impact: Purchase statutory summary and readiness flows include the document in TDS exposure
- Expected API behavior: Backend computes TDS centrally and returns runtime snapshot or reason code
- Expected UI behavior: TDS preview or posted snapshot shows section, rate, and deduction amount from backend
- Negative checks: Manual TDS edits that conflict with section policy, threshold, or PAN rules must fail

### Test ID: `PUR-TDS-002`
- Module: Purchase
- Scenario: No-PAN or threshold-driven TDS controls
- Input data: TDS section requiring PAN, vendor without PAN or threshold not crossed, open-period purchase
- Expected validation: No-PAN higher rate or no-deduction reason selected by withholding resolver
- Expected accounting entry: Either higher TDS payable line or no TDS line depending on resolved policy outcome
- Expected statutory impact: Runtime withholding reason code preserved for readiness and audit
- Expected report impact: Readiness dashboard and purchase statutory views reflect blocked, pending, or not-applicable state correctly
- Expected API behavior: Backend returns explicit reason codes instead of silent zeroing
- Expected UI behavior: User sees backend reason such as threshold not reached or PAN missing
- Negative checks: UI must not be able to bypass higher-rate or no-deduction reasoning

## Purchase TDS Compliance Map

| Case | Scenario | Mapped test coverage | Status | Core outcome covered |
| --- | --- | --- | --- | --- |
| `D01` | Vendor with PAN, section `194C` contractor | `purchase/tests.py`, `withholding/tests.py` | Automated | Section `194C` invoice-basis computation, cumulative threshold behavior, and normal PAN-based rate handling are covered |
| `D02` | Vendor without PAN, higher TDS rate | `purchase/tests.py`, `withholding/tests.py` | Automated | No-PAN higher rate under `206AA` is covered through resolver and purchase-side runtime snapshot tests |
| `D03` | Section `194J` professional fees | `purchase/tests.py`, `withholding/tests.py` | Automated | Professional-fee threshold and amount computation for invoice-stage TDS are covered |
| `D04` | Section `194I` rent | `purchase/tests.py`, `withholding/tests.py` | Automated | Rent threshold and rate subtype behavior, including plant-and-machinery vs office-rent logic, are covered |
| `D05` | Section `194H` commission | `purchase/tests.py`, `withholding/tests.py` | Automated | Explicit purchase withholding computation now proves `194H` threshold and commission-rate deduction on invoice-stage purchase flow |
| `D06` | Section `194A` interest | `purchase/tests_e2e_api.py`, `payments/tests.py`, `withholding/tests.py` | Automated | Payment-stage purchase settlement now explicitly proves `194A` runtime withholding through full-payment, partial-payment, and advance-payment voucher flows |
| `D07` | Section `194Q` purchase of goods | `purchase/tests.py`, `withholding/tests.py` | Automated | `194Q` eligibility gates, turnover gate, import exclusion, service exclusion, and resident-vendor applicability are covered |
| `D08` | Threshold not crossed: no TDS | `purchase/tests.py` | Automated | Explicit invoice-basis below-threshold no-deduction behavior is covered |
| `D09` | Threshold crossed by current invoice: TDS applies only as configured | `purchase/tests.py` | Automated | Single-invoice threshold crossing for invoice-basis sections is covered |
| `D10` | Threshold already crossed: TDS applies | `purchase/tests.py` | Automated | Cumulative threshold crossing for `194C` is covered through threshold service integration |
| `D11` | TDS on invoice booking | `purchase/tests.py`, purchase posting tests | Automated | Invoice-stage TDS computes centrally and posting reduces vendor payable with TDS payable credit |
| `D12` | TDS on payment | `purchase/tests_e2e_api.py`, `payments/tests.py`, `withholding/tests.py` | Automated | Purchase invoice to payment-voucher statutory lifecycle now proves runtime TDS adjustment, net settlement support, and full open-item closure |
| `D13` | Advance payment with TDS | `purchase/tests_e2e_api.py`, `payments/tests.py` | Automated | Advance payment voucher with runtime withholding now proves TDS adjustment persistence and vendor advance balance creation for the effective support amount |
| `D14` | Partial payment with TDS | `purchase/tests_e2e_api.py`, `payments/tests.py` | Automated | Partial payment voucher with runtime withholding now proves partial AP settlement, correct residual vendor outstanding, and persisted payment-stage TDS snapshot |
| `D15` | Lower deduction certificate | `withholding/tests.py` | Automated | Valid lower-deduction certificate overrides normal and higher rates when active |
| `D16` | Nil deduction certificate | `withholding/tests.py` | Automated | Nil deduction is supported through lower-certificate rate resolution when the active lower rate is zero |
| `D17` | TDS reversal through debit or credit note | `purchase/tests.py`, `purchase/tests_e2e_api.py` | Automated | Purchase credit-note lifecycle now explicitly proves TDS-booked invoices reverse through linked notes without creating a fresh TDS deduction, while AP open-item snapshots stay consistent with the current note policy |
| `D18` | TDS correction in filed or locked period | `purchase/tests_e2e_api.py`, `purchase/tests.py` | Automated | Filed-period TDS-booked purchase invoices now explicitly prove the original posted invoice and TDS snapshot stay unchanged while the linked current-period credit note carries correction audit metadata and no fresh TDS deduction |
| `D19` | TDS challan payment | `purchase/tests.py` statutory challan service tests | Automated | TDS challan deposit, audit trail, and state transitions are covered |
| `D20` | TDS payable report | `purchase/tests.py`, `withholding/tests.py` | Automated | Purchase statutory readiness and challan or return preview flows cover section totals, exclusions, and payable-style visibility |
| `D21` | Vendor ledger after TDS deduction | `purchase/tests.py` posting adapter tests | Automated | Vendor payable is explicitly proven net of TDS at invoice posting |
| `D22` | TDS should not reduce GST taxable value incorrectly | `purchase/services/purchase_invoice_service.py`, `purchase/tests.py` | Automated | TDS is computed from withholding service inputs without mutating GST taxable value or line GST computation |
| `D23` | TDS should not affect ITC claim incorrectly | `purchase/tests.py`, `purchase/tests_e2e_api.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Explicit `GSTR-3B` summary coverage now proves purchase-side TDS deduction does not reduce eligible ITC buckets or distort net ITC claims |

Expected outcome alignment for `D01` to `D23`:
- Section-wise threshold checked: covered through `194C`, `194J`, `194I`, and `194Q` resolver and threshold tests in `purchase/tests.py` and `withholding/tests.py`
- PAN missing higher rate applied: covered through `withholding/tests.py` resolver tests and purchase runtime snapshot coverage
- Lower or nil certificate respected: covered through resolver rate-selection tests in `withholding/tests.py`
- Vendor payable net of TDS: covered through purchase posting adapter tests in `purchase/tests.py`
- TDS payable ledger correct: covered through purchase posting adapter tests and section-specific payable mapping tests in `purchase/tests.py`
- TDS report or challan mapping correct: covered through challan deposit, eligible-line preview, section summary, exclusions, and readiness dashboard tests in `purchase/tests.py` and `withholding/tests.py`

## Sales TCS Compliance Map

| Case ID | Scenario | Evidence | Status | Notes |
| --- | --- | --- | --- | --- |
| `E01` | Customer eligible for TCS `206C(1H)` | `sales/tests.py`, `withholding/tests.py`, `receipts/tests.py` | Automated | Invoice-side TCS enablement and receipt-stage runtime collection for TCS-enabled flows are covered, including `206C(1H)` runtime snapshot evidence |
| `E02` | Customer threshold not crossed: no TCS | `sales/tests.py`, `withholding/tests.py` | Automated | Sales runtime snapshot coverage explicitly proves zero TCS with `BELOW_THRESHOLD_CUMULATIVE` reason when cumulative threshold is not crossed |
| `E03` | Customer threshold crossed: TCS applies | `sales/tests.py`, `receipts/tests.py` | Automated | Sales withholding unit coverage now explicitly proves cumulative-threshold-crossed `206C(1H)` computation produces positive TCS and the expected threshold-crossed reason code |
| `E04` | Customer without PAN higher TCS rate | `withholding/tests.py`, `sales/tests.py`, `sales/services/sales_withholding_service.py` | Automated | Sales-invoice TCS now resolves customer withholding profile and higher-rate logic through the shared resolver, and unit coverage explicitly proves the `206AA` no-PAN higher rate on customer-side TCS computation |
| `E05` | TCS on receipt | `receipts/tests.py` | Automated | Receipt runtime withholding explicitly adds auto-TCS adjustment rows and runtime status snapshot on receipt workflows |
| `E06` | TCS on advance receipt | `receipts/tests.py` | Automated | Receipt runtime withholding now explicitly proves unallocated advance receipts use cash received as the TCS base and create a collected runtime TCS row |
| `E07` | TCS on partial receipt | `sales/tests.py`, `receipts/tests.py` | Automated | Receipt runtime withholding now explicitly proves partial allocated receipts compute TCS on the partial receipt base and persist collected runtime status |
| `E08` | TCS on multi-invoice receipt | `receipts/tests.py` | Automated | Receipt runtime withholding now explicitly proves one receipt allocated across multiple invoices computes TCS from the summed allocation base and persists one collected runtime TCS row |
| `E09` | Sales return adjustment | `sales/tests.py`, `withholding/tests.py` | Automated | Sales service coverage now explicitly proves an inventory-affecting quantity-return credit note follows TCS reverse policy, retains sales-return context, and marks TCS as reversal on the adjustment document |
| `E10` | Credit note adjustment | `sales/tests.py`, `withholding/tests.py` | Automated | Sales credit-note TCS policy and note-level runtime reason persistence are explicitly covered |
| `E11` | TCS reversal | `sales/tests.py`, `withholding/tests.py` | Automated | Posting adapter and policy tests prove TCS payable reversal on credit notes when reversal policy applies |
| `E12` | TCS payable payment | `withholding/tests.py` | Automated | TCS deposit allocation, deposit confirmation, and deposit-status gating cover the payable-to-deposit lifecycle |
| `E13` | TCS ledger report | `withholding/tests.py` | Automated | TCS report ledger, workspace, and section-summary views are covered through filing-pack and reporting tests |
| `E14` | TCS `27EQ` export/preparation | `withholding/tests.py` | Automated | `27EQ` filing-pack preparation, validation, and export workflow are covered |
| `E15` | Customer exemption declaration | `sales/tests.py`, `withholding/tests.py` | Automated | Shared withholding resolver already honors exempt party profiles, and sales-side TCS coverage now explicitly proves an exempt customer profile suppresses TCS collection with the `EXEMPT` reason code |
| `E16` | Multi-branch TCS aggregation | `withholding/tests.py`, `withholding/services.py` | Automated | Cumulative `206C(1H)` helper coverage now explicitly proves entity-level prior TCS computations aggregate across branches while still allowing subentity-specific or entity-level threshold openings |
| `E17` | TCS should not affect GST taxable value incorrectly | `sales/tests.py`, `receipts/tests.py` | Automated | Sales service coverage now explicitly proves TCS collection updates customer receivable only and does not mutate taxable value, GST totals, or invoice grand total |

Expected outcome alignment for `E01` to `E17`:
- Threshold checked on customer FY turnover or receipts: covered for both below-threshold and threshold-crossed cumulative `206C(1H)` outcomes
- PAN higher rate applied: covered through shared higher-rate resolver logic and explicit sales-invoice TCS proof for no-PAN customer handling
- Receipt-based trigger works: covered for runtime TCS collection on standard, advance, partial, and multi-invoice receipt flows
- TCS payable report correct: covered through TCS filing-pack, ledger-style views, and section summary tests in `withholding/tests.py`

## Sales GST Compliance Map

| Case ID | Scenario | Evidence | Status | Notes |
| --- | --- | --- | --- | --- |
| `F01` | Registered customer same-state sale | `SAL-GST-001`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_sales_register.py` | Automated | Same-state B2B invoice flow explicitly proves CGST or SGST split, posting flow, GSTR-1 classification, and sales-register drilldown |
| `F02` | Registered customer interstate sale | `SAL-GST-002`, `reports/gstr1/tests/test_gstr1_report.py`, `reports/tests_sales_register.py` | Automated | Interstate taxable invoice flow explicitly proves IGST path, posting flow, GSTR-1 classification, and sales-register visibility |
| `F03` | Unregistered customer B2C sale | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py`, `reports/tests_sales_register.py` | Automated | B2C classification is explicitly covered through B2CL or B2CS section routing, GSTR-3B outward summary, and sales-register filters |
| `F04` | Export with LUT | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Export-without-IGST routing is now explicitly proven in GSTR-1 table 6 and GSTR-3B outward zero-rated supplies |
| `F05` | Export without LUT | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Export-with-IGST routing is explicitly covered in GSTR-1 section classification and GSTR-3B outward zero-rated supplies |
| `F06` | SEZ sale with tax | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | SEZ-with-IGST routing is now explicitly proven in GSTR-1 table 6 and current GSTR-3B outward-taxable treatment |
| `F07` | SEZ sale without tax | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | SEZ-without-IGST routing is now explicitly proven in GSTR-1 table 6 and current GSTR-3B outward-taxable bucket behavior |
| `F08` | Exempt sale | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Exempt sales are explicitly covered through nil or exempt validation and outward nil or exempt summary classification |
| `F09` | Nil-rated sale | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Nil-rated sales are now explicitly proven in GSTR-1 table 8 and GSTR-3B outward nil/exempt/non-GST summary buckets |
| `F10` | Non-GST sale | `reports/gstr1/tests/test_gstr1_report.py`, `reports/gstr3b/tests/test_gstr3b_summary.py` | Automated | Non-GST sales are now explicitly proven in GSTR-1 table 8 and GSTR-3B outward nil/exempt/non-GST summary buckets |
| `F11` | Sales return | `sales/tests_e2e_api.py`, `sales/tests.py`, `reports/tests_sales_register.py`, `withholding/tests.py` | Automated | Inventory-affecting sales-return credit-note flow is now explicitly proven through API create/confirm/post coverage while preserving quantity-return context and separate reporting polarity |
| `F12` | Credit note | `SAL-GST-003`, `reports/tests_sales_register.py`, `reports/gstr1/tests/test_gstr1_report.py` | Automated | Linked sales credit notes are explicitly covered for original-invoice linkage, separate posting, current-period outward reduction, and distinct register rows |
| `F13` | Debit note | `sales/tests_e2e_api.py`, `reports/tests_sales_register.py` | Automated | Sales debit notes are explicitly covered for original-invoice linkage, positive reporting effect, and separate register rows |
| `F14` | Advance receipt and GST liability | `reports/gstr1/tests/test_gstr1_report.py`, `receipts/tests.py` | Partial | GSTR-1 table 11 advance-receipt reporting is explicit, but there is not yet one end-to-end sales GST liability scenario proving accounting plus statutory bucket impact together |
| `F15` | Advance adjustment against invoice | `reports/gstr1/tests/test_gstr1_report.py`, `receipts/tests.py` | Partial | Advance-adjustment grouping and receipt-allocation infrastructure are covered, but not yet one explicit GST-focused invoice-adjustment statutory lifecycle |
| `F16` | Filed-period sales correction | `sales/services/sales_invoice_service.py`, `sales/tests_e2e_api.py`, `reports/tests_sales_register.py` | Gap | Locked-period edit protection is present, but the repo does not yet have the same explicit current-period correction-document automation on sales that purchase now has |
| `F17` | E-invoice applicable transaction | `sales/tests.py`, `reports/tests_sales_register.py`, `SAL-CTRL-001` | Automated | Applicability derivation, artifact exposure, and statutory cancel gating are explicitly covered for e-invoice-aware sales documents |
| `F18` | E-way bill applicable transaction | `sales/tests.py`, `reports/tests_sales_register.py`, `SAL-CTRL-001` | Automated | Applicability derivation, transport or artifact exposure, and cancel blocking with active statutory artifacts are explicitly covered for e-way-bill-aware sales documents |

Expected outcome alignment for `F01` to `F18`:
- Correct output GST: covered for same-state, interstate, export-with-IGST, export-without-IGST, SEZ-without-IGST, exempt, and credit or debit-note reporting paths through `sales/tests_e2e_api.py`, `reports/gstr1/tests/test_gstr1_report.py`, and `reports/gstr3b/tests/test_gstr3b_summary.py`
- Correct customer receivable: covered for posted sales invoices, credit notes, debit notes, and runtime TCS or settlement flows through `sales/tests_e2e_api.py`, `sales/tests.py`, and `receipts/tests.py`
- Correct `GSTR-1`: covered through section classification, table views, validations, and sales register drilldown in `reports/gstr1/tests/test_gstr1_report.py`
- Correct `GSTR-3B`: covered for outward taxable, zero-rated, and nil or exempt sales buckets in `reports/gstr3b/tests/test_gstr3b_summary.py`
- Correct sales register: covered through `reports/tests_sales_register.py` for invoice rows, note polarity, drilldown lineage, and compliance-artifact exposure
- Filed-period correction in current period: not yet fully green on sales; current evidence only proves direct mutation blocking, not a dedicated current-period sales correction-document flow

### Test ID: `PUR-CTRL-001`
- Module: Purchase
- Scenario: Missing static account mapping during posting
- Input data: Purchase invoice otherwise valid but one required posting map or static account missing
- Expected validation: Post must fail with clear posting configuration error
- Expected accounting entry: No partial entry should be persisted
- Expected statutory impact: No statutory report should include an unposted invalid document as posted
- Expected report impact: Purchase register may show the draft or confirmed document by business state, but ledger-driven statutory totals must not treat it as posted
- Expected API behavior: Post endpoint returns clear error and keeps document non-posted
- Expected UI behavior: User sees actionable posting error and document remains available for correction
- Negative checks: Retrying post must not create duplicate or partial ledger rows

## Sales GST / TCS / Statutory Controls

### Test ID: `SAL-GST-001`
- Module: Sales
- Scenario: Registered customer same-state taxable sales invoice
- Input data: Customer with GSTIN, same-state bill-to and place of supply, taxable goods line, posted tax invoice
- Expected validation: Backend derives CGST and SGST totals and blocks client control over derived tax fields
- Expected accounting entry: Customer receivable debit, sales income credit, output CGST credit, output SGST credit
- Expected statutory impact: Outward taxable supply captured as domestic B2B invoice
- Expected report impact: GSTR-1 section classification, sales register totals, and drilldown data include the invoice
- Expected API behavior: Create, confirm, and post endpoints succeed and persist backend-derived totals
- Expected UI behavior: Tax totals are read-only and invoice can be found through list and invoice search after confirm or post
- Negative checks: Client cannot persist overridden backend-controlled totals or tax regime fields

### Test ID: `SAL-GST-002`
- Module: Sales
- Scenario: Interstate taxable sales invoice
- Input data: Customer in another state, interstate place of supply, taxable invoice
- Expected validation: Backend chooses IGST path and no CGST or SGST totals
- Expected accounting entry: Customer receivable debit, sales income credit, output IGST credit
- Expected statutory impact: Outward interstate supply classified correctly
- Expected report impact: GSTR-1 table classification and sales register show interstate document and IGST totals
- Expected API behavior: Backend recomputes inconsistent tax split from line data and regime
- Expected UI behavior: Interstate regime reflected in derived summary fields and reports drill down to the invoice
- Negative checks: Same-state split must not survive save or post on interstate supply

### Test ID: `SAL-GST-003`
- Module: Sales
- Scenario: Sales credit note linked to original taxable invoice
- Input data: Posted original sales invoice, linked credit note in open period, taxable amount reversal
- Expected validation: Original invoice reference required; posted invoice itself cannot be silently edited
- Expected accounting entry: Sales reversal debit, output tax reversal debit, customer receivable credit
- Expected statutory impact: Current-period outward tax reduction through credit note, not through mutation of original invoice
- Expected report impact: GSTR-1 note sections and sales register show original and linked note distinctly
- Expected API behavior: Credit-note create endpoint requires original invoice and post flow succeeds separately
- Expected UI behavior: Credit note creation flow requires original reference and shows note as separate document
- Negative checks: Unlinked credit note for original-invoice-required flow must fail

### Test ID: `SAL-TCS-001`
- Module: Sales
- Scenario: TCS-applicable sales invoice
- Input data: Sales invoice with TCS-enabled entity config, supported TCS section, taxable base above applicable threshold
- Expected validation: TCS computed by sales withholding service, invoice context excludes payment-basis-only sections
- Expected accounting entry: Net customer receivable debit including TCS, sales income credit, output GST credits, TCS payable credit without duplicate customer TCS line
- Expected statutory impact: TCS exposure created with rate, base, amount, and reason snapshot
- Expected report impact: TCS workspace, ledger, and filing pack can include the computation after collection workflow progresses
- Expected API behavior: Backend persists TCS runtime snapshot on invoice and returns computed amount
- Expected UI behavior: TCS values display from backend and remain consistent after save or post
- Negative checks: Payment-based section in invoice context or config-disabled TCS must produce zero amount with explicit reason

### Test ID: `SAL-TCS-002`
- Module: Sales
- Scenario: TCS reversal policy on sales credit note
- Input data: Original TCS-bearing invoice, sales credit note, entity policy allowing reverse or disallow behavior
- Expected validation: TCS credit-note policy enforced centrally
- Expected accounting entry: When reverse policy applies, TCS payable reverses with the note; when disallowed, no TCS reversal entry is created
- Expected statutory impact: TCS reversal exposure or disallow reason preserved on note snapshot
- Expected report impact: TCS workspace and filing pack treat reversal row distinctly and avoid false open exceptions for zero-exposure reversal rows
- Expected API behavior: Backend computes note-level TCS result and persists runtime reason code
- Expected UI behavior: User sees whether TCS reversal applied or was disallowed by policy
- Negative checks: Manual forcing of TCS reversal contrary to entity policy must not persist

### Test ID: `SAL-CTRL-001`
- Module: Sales
- Scenario: Cancel blocked until statutory artifacts are cancelled
- Input data: Posted sales invoice with active e-invoice IRN or e-way bill artifact, statutory-cancel-enforcement enabled
- Expected validation: Business cancel blocked until statutory cancellation prerequisites are satisfied
- Expected accounting entry: No reversal posting while statutory artifact remains active
- Expected statutory impact: Prevents mismatch between business cancellation and statutory portal state
- Expected report impact: Invoice remains active in sales and statutory reports until valid cancel flow completes
- Expected API behavior: Cancel action raises clear error and does not call posting reversal
- Expected UI behavior: Cancel action shows compliance-block message instead of silently cancelling
- Negative checks: Forced business cancel without statutory cancellation must fail

## Period Locks / Amendments / Reversals

### Test ID: `PER-PUR-001`
- Module: Purchase
- Scenario: Direct edit attempt on posted purchase in filed or locked period
- Input data: Posted purchase invoice in GST-filed or accounting-locked period; attempt to change vendor, tax treatment, supplier invoice number, quantity, rate, or posting date
- Expected validation: Direct mutation blocked for protected fields
- Expected accounting entry: Original posting remains unchanged
- Expected statutory impact: Original GST period remains unchanged
- Expected report impact: Purchase register, GSTR-3B, and ledgers keep original posted data intact
- Expected API behavior: Update endpoint returns validation error describing locked or filed period restriction
- Expected UI behavior: Protected fields are read-only or save fails with backend error if user attempts modification
- Negative checks: Draft-only edit behavior must not leak onto posted locked documents

### Test ID: `PER-PUR-002`
- Module: Purchase
- Scenario: Locked-period purchase cancellation through current-period correction note
- Input data: Posted purchase invoice in filed or locked period, cancel requested by authorized user, current open period available
- Expected validation: Direct delete or mutation blocked; linked reversal or credit-note path required
- Expected accounting entry: Original posting untouched; separate balanced correction entry posted in current open period
- Expected statutory impact: GST and ITC adjustment recognized in current period, not retroactively
- Expected report impact: Original invoice remains in original period; correction note appears in current purchase register and GSTR-3B adjustment bucket
- Expected API behavior: Cancel action returns linked correction document instead of mutating source
- Expected UI behavior: User sees original invoice remain posted and linked correction created for current period
- Negative checks: Locked posted invoice cannot be unposted or deleted directly

### Test ID: `PER-SAL-001`
- Module: Sales
- Scenario: Posted sales invoice edit and reversal safety
- Input data: Posted sales invoice with tax lines; user attempts direct edit or reverse without valid posted state
- Expected validation: Posted invoice cannot be edited; reverse action requires posted state
- Expected accounting entry: No entry changes on invalid edit attempt; valid reverse updates posting state through reversal flow
- Expected statutory impact: Sales statutory reports continue to reflect original invoice until valid note or reversal flow occurs
- Expected report impact: Sales register and GSTR-1 remain consistent with posting state
- Expected API behavior: Update on posted invoice fails; reverse on non-posted invoice fails; valid reverse updates entry state
- Expected UI behavior: Posted invoices are effectively locked for direct edit and reversal actions respect state checks
- Negative checks: Silent mutation of posted sales invoice totals or party fields must not occur

## Reports / Reconciliation / Statutory Returns

### Test ID: `RPT-GST-001`
- Module: Reports
- Scenario: GSTR-3B purchase-side summary with normal ITC, blocked ITC, and reverse charge
- Input data: Mix of regular taxable purchase, blocked ITC purchase, URD non-RCM purchase, import or RCM purchase, and purchase credit note
- Expected validation: Only eligible claimable inputs contribute to normal ITC; URD non-RCM excluded from normal ITC; current-period note adjustments reverse the correct bucket
- Expected accounting entry: Source ledger postings remain the basis of the report
- Expected statutory impact: Correct population of normal ITC, reverse-charge liability, and current-period adjustment buckets
- Expected report impact: GSTR-3B summary aligns with source document treatment and linked correction documents
- Expected API behavior: Summary endpoint returns bucket totals and respects scope and permissions
- Expected UI behavior: Dashboard totals and drilldowns tie back to posted source documents
- Negative checks: Composition, URD non-RCM, and domestic-import mismatches must not leak into normal claim buckets

### Test ID: `RPT-GST-002`
- Module: Reports
- Scenario: GSTR-1 outward summary, validations, and section drilldowns
- Input data: Mix of B2B, interstate, note, mixed-rate, and validation-warning sales documents in scope period
- Expected validation: Classification, POS, tax split, and note-linkage warnings appear where data is inconsistent
- Expected accounting entry: Underlying posted sales entries remain unchanged; report is a projection over posted documents
- Expected statutory impact: Outward supply and note buckets classified into the correct GSTR-1 sections
- Expected report impact: Summary, section APIs, and exports reconcile to the same invoice set
- Expected API behavior: Readiness, validations, summary, section, meta, and export endpoints enforce permissions and scope
- Expected UI behavior: Report screens show blocked or review readiness states with drilldowns and export actions
- Negative checks: Missing report permission or invalid scope must deny access

### Test ID: `RPT-GST-003`
- Module: Reconciliation
- Scenario: GST reconciliation candidate inclusion and exclusion rules
- Input data: Registered taxable purchase, URD non-RCM purchase, composition purchase, import purchase
- Expected validation: Only eligible source documents enter the normal reconciliation candidate pool
- Expected accounting entry: No journal change; reconciliation is an analytical layer
- Expected statutory impact: URD non-RCM, composition, and import purchases stay out of normal 2B matching unless explicit support exists
- Expected report impact: GST reconciliation and exception views show only relevant match candidates
- Expected API behavior: Provider or summary endpoints exclude unsupported sources consistently
- Expected UI behavior: Reconciliation grid does not surface excluded source types as normal match items
- Negative checks: Unsupported source types must not appear as claimable unmatched normal invoices

### Test ID: `RPT-TCS-001`
- Module: Withholding / TCS
- Scenario: TCS filing pack and deposit allocation lifecycle
- Input data: TCS computation rows, confirmed and draft deposits, filed and unfiled returns, reversal row with zero exposure
- Expected validation: Draft deposits cannot be allocated as filed; clean readiness snapshot required for validated or filed returns
- Expected accounting entry: Collection and deposit lifecycle does not distort original sales posting; allocations track statutory settlement state
- Expected statutory impact: Filing pack reflects computed, collected, deposited, and pending TCS correctly
- Expected report impact: Workspace, ledger report, filing-pack export, and return tracker align to the same computation set
- Expected API behavior: Allocation, confirm, filing-pack, and return endpoints enforce readiness and workflow locks
- Expected UI behavior: TCS workspace shows blocked, pending, and filed states with exportable tracker details
- Negative checks: Filed returns cannot be edited or deleted; correction return requires matching filed original return

### Test ID: `RPT-WHT-001`
- Module: Withholding / TDS readiness
- Scenario: Purchase withholding readiness dashboard
- Input data: Mix of posted and unposted purchase-side statutory exposures, missing PAN cases, non-target sections, and readiness exceptions
- Expected validation: Readiness status derived from posting state, section applicability, PAN availability, and target-section filters
- Expected accounting entry: No ledger mutation; readiness is analytical
- Expected statutory impact: Exposes transactions not ready for statutory filing or settlement
- Expected report impact: Readiness dashboard supports drilldowns and excludes non-target sections by default
- Expected API behavior: Dashboard requires entity scope and permission, returns row state plus drilldowns
- Expected UI behavior: Dashboard shows blocked, fix-now, and ready rows from backend state
- Negative checks: Missing permission or entity scope must deny access

## Ledger / Posting Integrity

### Test ID: `LEDGER-001`
- Module: Purchase and Sales Posting
- Scenario: Balanced posting and idempotent repost behavior
- Input data: One posted purchase and one posted sales document, plus repeated post attempt or repost flow
- Expected validation: Posting uses static account maps and existing posting services; repeated post must not duplicate active ledger impact
- Expected accounting entry: Every posting remains balanced with debit equal to credit and one active posting batch per business post
- Expected statutory impact: Report totals do not double-count repeated posting attempts
- Expected report impact: Purchase register, sales register, trial balance, and statutory summaries remain stable after repeated calls
- Expected API behavior: Repeated post either no-ops safely or returns controlled response without creating duplicate journal rows
- Expected UI behavior: User does not see duplicate ledger effects from repeated actions or refreshes
- Negative checks: Missing static account map must fail clearly and repeated calls must not create duplicate entries

### Test ID: `LEDGER-002`
- Module: Purchase and Sales Drilldown
- Scenario: Ledger and report drilldown remains linked to source document and linked correction document
- Input data: Original posted invoice and current-period linked note for both purchase or sales side where supported
- Expected validation: Linked source document identifiers persist across reporting and accounting layers
- Expected accounting entry: Original and correction entries remain separate balanced postings
- Expected statutory impact: Original and amendment periods remain distinct
- Expected report impact: Registers and statutory drilldowns show both original and correction document lineage correctly
- Expected API behavior: Detail and drilldown endpoints include posting lookup or source linkage metadata where supported
- Expected UI behavior: User can trace from report row to source document and correction note without ambiguity
- Negative checks: Corrections must not overwrite original ledger drilldown identity

## Current Open Gaps To Track Separately

- `OPEN-001`: Multi-GSTIN entity end-to-end statutory behavior needs a product-model decision before automation can prove it safely.
- `OPEN-002`: Future-dated purchase invoice policy still needs explicit product confirmation before it should be codified as a green statutory scenario.
