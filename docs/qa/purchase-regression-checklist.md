# Finacc Purchase Regression Checklist

Run this checklist before merging purchase-flow changes.

## Automated suites

- Run purchase service tests covering validation, totals, posting, ITC, RCM, and duplicate detection.
- Run purchase API end-to-end tests for create, update, confirm, post, cancel, and historical snapshot behavior.
- Run GSTR-3B summary tests for normal ITC, blocked ITC, and RCM sections.
- Run purchase register tests for totals, GST fields, and historical document snapshot behavior.
- Run GSTR-2B reconciliation tests for candidate inclusion and exclusion rules.
- Run Angular specs that normalize purchase payloads and derive GST state defaults.
- Run Angular purchase UI-contract specs for read-only vendor, GST treatment, reverse charge, and place-of-supply controls.

## High-risk regression areas

- Registered vendor without GSTIN must fail before invoice save or post.
- Unregistered non-RCM purchase must not create supplier GST or normal ITC.
- Composition vendor purchase must not create claimable supplier GST ITC.
- Import goods purchase must stay out of normal supplier-GST ITC buckets.
- Import service purchase must require header-level reverse charge.
- SEZ purchase must stay in the INTER regime for both taxable and non-taxed variants.
- RCM purchase must not expose ITC before the payment gate is satisfied.
- RCM purchase credit note must preserve reverse-charge context and reverse the RCM payable polarity correctly.
- Mixed goods and service invoices must keep aggregate totals correct and hand both line types to posting.
- Duplicate supplier invoice rule must block same vendor, invoice number, invoice date, and amount.
- Credit-day purchase invoices must derive due dates correctly and create AP open items with the same due date.
- Do not assume “cash purchase” is a header flag; current behavior is purchase posting plus payment-voucher settlement, and automated coverage now proves the immediate cash-settlement path through payment vouchers.
- Multi-invoice vendor settlement must reduce the outstanding balance of each targeted purchase open item correctly.
- Posted document repost or repeated post call must not duplicate ledger entries.
- Locked-period mutation must be blocked consistently in service and API flows.
- Posted locked-period cancel must create a current-period linked credit note without mutating the source invoice.
- Locked-period unpost must stay blocked and direct users to correction-document flow.
- Quantity-return notes must not exceed remaining returnable quantity.
- Value-only note reasons must not create inventory reversal.
- Value-only note creation must not consume quantity-return capacity for the original invoice.
- Quantity-return notes must stay location-aware and block once downstream OUT movements have consumed the original stock.

## Cross-module reconciliation

- Purchase grand total matches posting total.
- Posting balances debit and credit.
- Vendor outstanding matches AP ledger.
- GST input and liability totals match statutory reports.
- Purchase register totals match report exports and drilldown.

## Manual smoke pass

- Create one registered taxable purchase and post it.
- Create one URD non-RCM purchase and confirm GST suppression.
- Create one composition vendor purchase and confirm ITC is blocked.
- Create one import or SEZ purchase and confirm the INTER regime and reporting path.
- Create one RCM purchase, pay RCM tax, then confirm claimability transition.
- Create one TDS purchase and settle payment.
- Create one vendor settlement spanning multiple purchase invoices and confirm outstanding totals reconcile.
- Create one stock purchase and one purchase return.
- Create one same-day cash purchase using posted purchase plus immediate payment voucher and confirm the AP open item closes fully.
- Cancel one posted purchase and confirm reversal entries.
- Cancel one posted locked-period purchase and confirm the original stays posted while the linked correction note lands in the current open period.

## Scope guardrails

- Reverse charge is still validated at purchase-header level in this release.
- Do not regress existing header-level RCM behavior while mixed line-level RCM remains out of scope.
