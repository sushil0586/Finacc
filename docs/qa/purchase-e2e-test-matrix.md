# Finacc Purchase E2E Test Matrix

Status legend:
- `Automated`: covered by the current automated backend, API, reporting, import, reconciliation, or Angular test suite.
- `Partial`: some automated coverage exists, but not yet as a clean standalone scenario end to end.
- `Manual`: intentionally left to the QA checklist for now.
- `Gap`: not yet proven adequately in automation or manual matrix detail.

## Scenario Coverage

| # | Scenario | Expected outcome | Status | Notes |
| --- | --- | --- | --- | --- |
| 1 | Registered GST vendor, same-state purchase | Valid GSTIN accepted and intra-state tax path uses CGST/SGST | Automated | Covered through vendor validation and intra-state GST behavior |
| 2 | Registered GST vendor, interstate purchase | Valid GSTIN accepted and interstate tax path uses IGST | Automated | Covered through inter-state regime behavior |
| 3 | Registered vendor without GSTIN | Invoice save or post blocked by policy | Automated | Explicit validation covered |
| 4 | Vendor GSTIN inactive/cancelled | Configured warning or block behavior triggered | Automated | Policy-driven warning and block coverage exists |
| 5 | Unregistered vendor, no GST, no RCM | No supplier GST and no normal ITC | Automated | URD non-RCM suppression covered |
| 6 | Unregistered vendor with RCM | Header-level RCM liability and deferred ITC path | Automated | Current model is intentionally header-level only |
| 7 | Composition vendor purchase | No normal supplier GST ITC claim path | Automated | Composition ITC block and reconciliation exclusion covered |
| 8 | SEZ vendor with tax | Explicit SEZ treatment with taxable reporting path | Automated | Dedicated purchase API coverage now proves SEZ taxable purchase creation under INTER and IGST totals |
| 9 | SEZ vendor without tax | Explicit SEZ treatment without normal domestic tax behavior | Automated | Dedicated purchase API coverage now proves SEZ non-taxed purchase creation with zero GST totals |
| 10 | Import of goods | Not treated as normal domestic supplier-GST purchase | Automated | Import goods kept out of normal supplier-GST ITC path |
| 11 | Import of services with RCM | Import-service purchase requires reverse charge | Automated | Explicit validation covered |
| 12 | Exempt goods purchase | No normal GST claim and correct exempt reporting | Automated | Covered by taxability rule coverage |
| 13 | Nil-rated goods purchase | No normal GST claim and correct nil-rated reporting | Automated | Covered by taxability rule coverage |
| 14 | Non-GST purchase | No GST and correct non-GST reporting path | Automated | Covered by taxability rule coverage |
| 15 | Inventory stock purchase | Stock quantity, valuation, and posting update correctly | Automated | Inventory move and posting path covered |
| 16 | Service/expense purchase | Expense behavior without stock movement | Automated | Service and expense purchase behavior covered |
| 17 | Fixed asset purchase | Asset posting and asset-intake path work correctly | Automated | Asset intake path covered |
| 18 | Mixed goods and service invoice | Mixed lines allowed and totals/posting stay correct | Automated | Purchase API coverage now proves mixed goods and service lines save together, totals aggregate correctly, and posting receives both line types |
| 19 | Purchase with freight/packing/insurance | Charge rows post correctly and tax treatment remains correct | Automated | Charges coverage exists |
| 20 | Purchase with line discount | Line discount reduces taxable value correctly | Automated | Discount recalculation covered |
| 21 | Purchase with header discount | Header discount reduces taxable value correctly | Automated | Discount recalculation covered |
| 22 | Purchase with round-off | Round-off ledger and totals behave correctly | Automated | Round-off coverage exists |
| 23 | Purchase with TDS deduction | TDS payable and vendor payable behave correctly | Automated | TDS workflow covered |
| 24 | Purchase with advance adjustment | Advance settlement updates AP correctly | Automated | Advance-adjustment path covered |
| 25 | Cash purchase | Cash-settlement purchase flow behaves correctly | Automated | Purchase API coverage now proves posted purchase plus immediate AGAINST_BILL payment-voucher settlement closes the AP open item without needing a distinct purchase-header type |
| 26 | Credit purchase | AP-based credit purchase flow behaves correctly | Automated | Credit-days coverage now proves due-date derivation and AP open-item creation for an unpaid posted purchase |
| 27 | Partial vendor payment | Partial settlement reduces outstanding correctly | Automated | Payment behavior covered |
| 28 | Full vendor payment | Full settlement clears outstanding correctly | Automated | Payment behavior covered |
| 29 | Multi-invoice vendor payment | One payment can settle multiple purchase invoices correctly | Automated | AP settlement coverage now proves one vendor settlement can allocate across multiple purchase open items |
| 30 | Purchase return before stock consumption | Quantity return reverses stock and accounting safely | Automated | Service and API coverage now prove location-aware quantity-return notes are allowed while the original stock remains safely returnable |
| 31 | Purchase return after stock consumption | Unsafe silent stock reversal is prevented or redirected | Automated | Service and API coverage now block quantity-return notes once downstream OUT movements have consumed the original stock, with guidance to use a value-only note or inventory adjustment flow |
| 32 | Value-only debit note | Value adjustment does not reverse stock quantity | Automated | Value-only note behavior covered |
| 33 | Quantity debit/credit note | Quantity-linked correction respects stock and source limits | Automated | Create-note lifecycle now proves quantity-return notes consume remaining returnable quantity while value-only notes do not |
| 34 | Rate difference debit/credit note | Rate-only correction adjusts value without corrupting stock | Automated | Rate-difference path covered |
| 35 | RCM purchase credit note | RCM correction unwinds liability and ITC correctly | Automated | GSTR-3B current-period reverse-charge adjustment is covered, purchase API note creation preserves RCM context, and posting adapter polarity is explicitly verified for RCM credit notes |
| 36 | Filed-period purchase correction | Correction posts through current-period linked document only | Automated | Filed-period amendment flow covered |
| 37 | Locked-period invoice edit attempt | Direct mutation is blocked | Automated | Service and API coverage exists |
| 38 | Locked-period invoice cancel | Cancel routes to current-period linked correction note | Automated | Explicitly tested |
| 39 | Duplicate supplier invoice | Same vendor plus number plus date plus amount is blocked | Automated | Explicit validation covered |
| 40 | Bulk import with valid invoices | Valid import rows create usable purchase documents | Automated | Import happy path covered |
| 41 | Bulk import with invalid GSTIN | Row validation blocks invalid GSTIN rows clearly | Automated | Import validation covered |
| 42 | Bulk import with duplicate invoice | Duplicate rows are rejected clearly | Automated | Import validation covered |
| 43 | Bulk import URD vendor with GST amount | Invalid URD tax charging is blocked clearly | Automated | Import URD validation covered |
| 44 | Bulk import RCM invoice missing place of supply | Missing place of supply is rejected | Automated | Import validation covered |
| 45 | Multi-branch purchase | Branch or subentity scoped purchase behavior stays correct | Automated | Subentity and scope behavior covered |
| 46 | Multi-GSTIN entity purchase | Correct GST registration context is applied per entity scope | Gap | Current operating model still allows only one active GST registration per entity, so this needs a product-model decision before purchase automation can prove it end to end |
| 47 | Warehouse purchase | Warehouse or location inventory handling stays correct | Automated | Warehouse or location behavior covered |
| 48 | Purchase with missing static account mapping | Clear posting error is raised | Automated | Explicit error coverage exists |
| 49 | User without GST permission tries to edit tax treatment | API and UI block sensitive GST edits | Automated | Restricted-field behavior covered |
| 50 | User without cancel permission tries to cancel posted invoice | Permission family blocks cancel action | Automated | Permission coverage exists |
| 51 | Vendor master changed after invoice posting | Historical invoice snapshot remains stable | Automated | Historical vendor snapshot test exists |
| 52 | Item tax rate changed after invoice posting | Historical item-tax behavior remains stable | Automated | Purchase line tax snapshot remains stable even after product GST master changes |
| 53 | Purchase invoice date in previous FY | Outside-FY date is blocked correctly | Automated | Outside-FY validation covered |
| 54 | Purchase invoice date in future | Future-dated purchase behavior follows explicit policy | Gap | No explicit scenario proof yet |
| 55 | Purchase after GST return filing | Filed-period protection or correction flow is enforced | Automated | Dedicated purchase API coverage now proves create-credit-note from filed-period invoice lands in the current open period |
| 56 | Purchase before financial year start | Pre-FY-start date is blocked correctly | Automated | Outside-FY validation covered |
| 57 | Cancel draft purchase | Draft cancel is allowed without posted reversal behavior | Automated | Draft cancel behavior covered |
| 58 | Edit draft purchase | Draft edit remains allowed | Automated | Draft edit behavior covered |
| 59 | Edit posted purchase | Posted invoice cannot be silently changed | Automated | Explicitly blocked without correction flow |
| 60 | Repost/idempotency check | Reposting does not duplicate active ledger impact | Automated | Explicit regression item covered |

## Totals

- `Automated`: 58
- `Partial`: 0
- `Manual`: 0
- `Gap`: 2

## Current Priorities

1. Close the pure test gaps first:
   `46`, `54`
2. Keep operational smoke checks focused on cross-module parity for the automated flows while the pure product gaps remain open.

## Scope Notes

- Reverse charge remains a header-level decision in the current purchase model.
- Mixed RCM and non-RCM lines on the same invoice remain intentionally out of scope.
- Filed-period or locked-period posted purchases now correct through current-period linked notes; original invoices remain unchanged.
