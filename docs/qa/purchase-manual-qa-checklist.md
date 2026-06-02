# Finacc Purchase Manual QA Checklist

Use this checklist after any change to purchase validation, posting, GST, ITC, RCM, TDS, inventory, or reporting.

## Core setup

- Create vendors for registered, unregistered, composition, SEZ, import, exempt, and TDS-applicable cases.
- Create items for goods, services, expenses, assets, inventory, non-inventory, exempt, nil-rated, and non-GST cases.
- Ensure static account mappings exist for purchase, expense, inventory, asset, GST, RCM, TDS, round-off, freight, and payable ledgers.
- Keep at least one open period and one locked or filed period available for validation checks.

## Vendor master

- Verify registered vendors require GSTIN.
- Verify unregistered vendors can be saved without GSTIN.
- Verify composition vendors can be maintained without enabling normal ITC behavior on purchase invoices.
- Verify SEZ and import vendor setups default downstream invoices into the expected tax-treatment path.
- Verify invalid GSTIN format or wrong state code is rejected.
- Verify inactive GSTIN raises the configured warning or block behavior.
- Verify vendor tax treatment changes new-invoice defaults but does not mutate old invoices.
- Verify changing a product GST master after invoice creation does not silently rewrite stored purchase-line tax values.

## Purchase creation

- Create draft purchases for goods, service, expense, asset, inventory, and mixed-line invoices.
- Verify supplier invoice number and supplier invoice date are mandatory.
- Verify duplicate detection blocks same vendor plus supplier invoice number plus supplier invoice date plus amount.
- Verify same supplier invoice number for different vendors is still allowed unless business policy says otherwise.
- Verify totals recalculate correctly after line edits, discounts, charges, and round-off.
- Verify mixed goods-plus-service invoices still render correctly in UI even though backend/API coverage already proves totals and posting input.

## GST and ITC

- Verify same-state purchase creates CGST and SGST, and interstate purchase creates IGST.
- Verify unregistered non-RCM purchase does not calculate supplier GST.
- Verify composition or blocked-credit scenarios do not create normal claimable ITC.
- Verify composition vendor purchases stay out of normal 2B-style ITC claim flows.
- Verify import goods purchases do not behave like domestic supplier-GST invoices.
- Verify import service purchases require header-level reverse charge and place of supply.
- Verify SEZ purchases respect explicit tax treatment and INTER regime behavior.
- Verify both taxed and non-taxed SEZ purchase variants behave correctly and keep the expected GST totals.
- Verify ITC status is visible and consistent in invoice, posting, and reporting flows.
- Verify 2B reconciliation screens exclude URD non-RCM purchases.

## RCM lifecycle

- Create URD RCM and registered RCM purchases with valid HSN or SAC, tax rate, and place of supply.
- Verify purchase posting creates reverse-charge liability.
- Verify ITC remains pending until the related tax payment step is completed.
- Verify GSTR-3B reflects RCM liability in the correct bucket.
- Verify return or note against an RCM purchase unwinds liability and ITC correctly, including value-only credit note behavior that keeps the document in reverse-charge mode.

## TDS lifecycle

- Create service and rent purchases for TDS-applicable vendors.
- Verify threshold and section-based deduction behavior.
- Verify PAN-missing case uses higher-rate behavior where configured.
- Verify vendor payable is reduced only when deduction is booked at invoice or payment as configured.
- Verify TDS reports reconcile with purchase and payment documents.

## Inventory and assets

- Verify stock quantity and valuation update for stock purchases.
- Verify non-stock and asset lines do not create stock movement.
- Verify freight can be capitalized or expensed based on setup.
- Verify eligible GST does not inflate inventory cost, but blocked or ineligible tax can be capitalized where configured.
- Verify asset purchases feed the correct asset value into downstream capitalization or depreciation flows.

## Returns and reversals

- Create full and partial purchase returns linked to original invoices.
- Verify returned quantity or value cannot exceed source document availability.
- Verify debit note value-only and rate-difference flows work without corrupting stock.
- Verify filed-period or locked-period returns route through amendment or current-period reporting behavior.
- Verify note or return creation from a filed-period purchase does not silently rewrite the original posted document.
- Verify cancelling a posted locked-period purchase creates a linked current-period credit note instead of mutating the original invoice.
- Verify auto-created locked-period reversal uses `note_reason=other` and does not reverse stock quantity silently.
- Verify quantity-return notes in locked-period scenarios still cap against remaining returnable quantity.
- Verify value-only price-difference notes keep stock quantity unchanged.
- Verify a price-difference note does not consume the remaining quantity-return capacity of the original purchase.
- Verify a quantity-return purchase note raised before any downstream issue or sale is allowed only when the original stock remains safely returnable at the selected location.
- Verify a quantity-return purchase note raised after downstream consumption is blocked with guidance to use a value-only note or inventory adjustment flow.
- Verify cancellation and reversal entries balance and remove no audit trail.

## Payments and reconciliation

- Verify full, partial, advance, and adjusted payments update vendor outstanding correctly.
- Verify same-day cash purchase operational flow behaves correctly when the business uses an immediate payment voucher after purchase posting.
- Verify one vendor settlement can allocate across multiple purchase invoices and reduce each open-item balance correctly.
- Verify payment with TDS deduction reduces vendor balance and creates TDS payable correctly.
- Verify overpayment behavior follows product policy.
- Verify vendor ledger, purchase register, trial balance, and GST reports reconcile back to the same source document.
- Verify report drilldowns open the correct purchase document.

## Security and permissions

- Verify maker can create but not post when role separation is enabled.
- Verify checker or admin-only actions are blocked at API and UI for restricted users.
- Verify restricted users cannot change GST treatment, enable reverse charge, or swap vendor GST status from the purchase screen.
- Verify restricted users cannot edit GST, ITC, or locked-period data.
- Verify restricted users cannot trigger locked-period auto reversal unless they also hold credit-note create and post rights.
- Verify users cannot access purchases outside their entity or branch scope.
- Verify audit history captures sensitive edits, cancellations, and reversals.
