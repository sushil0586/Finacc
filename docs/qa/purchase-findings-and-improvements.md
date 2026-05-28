# Finacc Purchase Findings And Improvements

## What was tightened in this pass

- Registered vendors now require GSTIN at purchase-service validation time.
- Inactive vendor GSTIN can now raise a policy-driven warning during purchase validation.
- Supplier invoice number and supplier invoice date are enforced centrally in the purchase service.
- Duplicate supplier invoice detection now blocks same vendor plus supplier invoice number plus supplier invoice date plus amount.
- Unregistered non-RCM purchases now suppress supplier GST, block normal ITC, stay out of GSTR-2B reconciliation, and stay out of GSTR-3B ITC-available totals.
- Composition vendor purchases now block normal supplier GST ITC, stay visible in purchase reporting, and stay out of normal 2B-style reconciliation selection.
- Import goods purchases now suppress domestic supplier-GST treatment and stay out of normal GSTR-3B ITC-available buckets.
- Import service purchases now require reverse charge in the reusable purchase and bulk-import validation paths.
- SEZ and import purchase validation now explicitly require the INTER regime in reusable service and import validation paths.
- Purchase import validation now covers registered vendor GSTIN requirements, URD-with-GST rejection, duplicate supplier invoices, invalid taxability, composition GST misuse, and import-service reverse-charge requirements row by row.
- Purchase-screen UI contract coverage now blocks restricted editing of vendor, GST treatment, reverse charge, and place-of-supply fields when the backend marks them read-only.
- Historical vendor snapshot behavior is now covered so later vendor-master changes do not silently rewrite old purchase documents.
- Historical product-tax snapshot behavior is now covered so later product GST master changes do not silently rewrite stored purchase-line tax values.
- SEZ purchase coverage is now explicit for both taxable and non-taxed purchase creation paths.
- Filed-period and locked-period purchases now resolve through reusable amendment-window logic instead of direct mutation.
- Posted locked-period cancel now creates a linked current-period credit note, keeps the original posting intact, and stores correction audit metadata on both documents.
- Locked-period unpost is now blocked and redirected to correction-document flow.
- Linked quantity-return notes now enforce remaining returnable quantity during create-note actions as well, while price-difference notes remain value-only and non-inventory.
- Filed-period create-credit-note flow is now explicitly covered so correction documents created from locked or filed purchases land in the current open period.
- Purchase credit-note factory now keeps monetary amounts positive and relies on document type for sign, aligning posting, AP, and reporting behavior.
- Reverse-charge credit note coverage now explicitly proves the correction document keeps header-level RCM context and the posting adapter flips RCM payable and input-tax polarity correctly on unwind.
- Mixed goods-and-service purchase coverage now explicitly proves both line types can coexist on one invoice while totals and posting input stay correct.
- Credit purchase coverage now explicitly proves `credit_days` derives `due_date` and the posted purchase creates the expected AP open item snapshot.

## Gaps still visible

- Reverse charge remains header-level by product choice in the current release; mixed RCM and non-RCM lines are intentionally out of scope.
- Capital-goods ITC is now covered as part of the current product behavior: asset purchases can remain ITC-eligible and their tax flows into the normal eligible ITC bucket in `GSTR-3B`, rather than a separate capital-goods bucket.
- Partial ITC is now supported through line and charge tax-summary splits, and `GSTR-3B` now uses those eligible versus ineligible tax splits instead of relying only on the document-level ITC flag.
- RCM ITC post-payment release is now supported through the existing AP settlement trail: any posted payment voucher that settles the invoice unlocks ITC claim for reverse-charge purchases.
- Filed-period return and amendment behavior is now partially automated, but broader cross-report evidence still needs expansion for trial balance, inventory valuation, and deeper ledger drilldown scenarios.
- MSME-specific compliance and reporting behavior is not clearly modeled end to end.
- Bulk purchase import coverage is stronger for validation errors, but downloadable error reporting and re-import idempotency still need broader checks.
- UI permission coverage is better for read-only purchase fields, but role-matrix breadth still needs expansion.
- Multi-invoice vendor settlement is now automated through the AP settlement flow, and cash-purchase coverage now proves the immediate payment-voucher path closes the AP open item for same-day settlement.
- Purchase return quantity limits are now enforced against both original source quantities and downstream stock consumption at the selected location, and auto-created return notes now preserve the source location by default.
- Multi-GSTIN purchase coverage is still blocked by the current entity model, which allows only one active GST registration per entity.
- Future-dated purchase behavior still needs an explicit product policy before it should be automated as pass/fail validation.

## Suggested service and model improvements

- Introduce an explicit purchase-tax-treatment snapshot on the document so historical GST behavior does not depend on live vendor master interpretation.
- Keep reverse-charge applicability centralized at header level unless product requirements explicitly expand to mixed RCM invoices.
- Centralize duplicate supplier invoice matching behind a dedicated domain service so imports, API create, and manual create use the exact same rule.
- Consider a dedicated amendment-event model if correction-history reporting needs first-class querying beyond `match_notes`.
- Separate ITC eligibility, ITC claim status, and 2B match policy into a narrower service boundary to simplify reporting and payment-gated RCM logic.
- Add a purchase posting idempotency test helper reused by invoice, notes, and return scenarios.
- Add a report parity test harness that compares purchase register, ledger totals, and GSTR summary totals from the same fixtures.

## Recommended next automation

- Add posting-level assertions for purchase return, debit note, and locked-period cancellation journal reversals.
- Add inventory valuation tests for landed-cost capitalization versus expense treatment.
- Add RCM lifecycle tests that include payment voucher linkage and post-payment ITC release.
- Add vendor-outstanding parity tests that exercise auto-created filed-period correction notes without mocked AP sync.
- Expand purchase-return inventory safety with richer downstream stock provenance if future product rules need to distinguish true source-stock consumption from later replenishments of the same item and batch.
- Add TDS tests for lower deduction certificate, threshold crossing across multiple invoices, and payment-time deduction mode.
- Add import tests for URD rows, invalid GSTIN rows, duplicate rows, and re-import idempotency.
