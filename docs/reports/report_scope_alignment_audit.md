# Report Scope Alignment Audit

## Purpose

This audit tracks which report screens already follow the common reporting scope rule in
[common_reporting_scope_rules.md](./common_reporting_scope_rules.md), which ones are intentionally
single-date `as_of` reports, and which ones still need alignment work.

The common rule being audited is:

- if only `anchor date` is used:
  - effective search window = `financial year start -> anchor date`
- if explicit `from_date` and `to_date` are used:
  - `Opening` = all posted balance from financial year start through `from_date - 1 day`
  - `Movement` = `from_date -> to_date`
  - `Closing = Opening + Movement`
- `effective start date` belongs to movement, not opening

## Fully Aligned

These reports are already aligned with the common rule in both intent and active implementation.

| Report | Frontend | Backend | Notes |
|---|---|---|---|
| Trial Balance | `financial-trial-balance.component.ts` | `reports/api/financial/views.py` | Anchor-only scopes resolve to FY start -> anchor. Custom range splits opening and movement. |
| Ledger Summary | `ledgersummary.component.ts` | `reports/api/financial/views.py`, `reports/services/financial/ledger_summary.py` | Anchor-only scopes behave as one continuous window. Custom range keeps separate opening. |
| Ledger Book | `ledgerbook.component.ts` | `reports/api/financial/views.py`, `reports/services/financial/ledger_book.py` | Anchor-only scopes use FY start -> anchor. Custom range keeps brought-forward opening separate. |
| Balance Sheet | `balancesheet.component.ts` | existing balance-sheet builders | Anchor-only scopes now use FY start -> anchor. |
| Profit & Loss | `incomeexpenditurereport.component.ts` | existing statements builder | Anchor-only scopes now use FY start -> anchor. |
| Trading Account | `tradingaccountstatement.component.ts` | existing statements builder | Anchor-only scopes now use FY start -> anchor. |
| Cashbook | `cashbook.component.ts` | cashbook API unchanged, explicit-date model already correct | Explicit range already uses FY start -> day before `from_date` for opening adjustment. |
| Vendor Ledger Statement | `vendor-ledger-statement.component.ts` | payables statement API | Explicit range already uses FY start -> day before `from_date` for opening adjustment. |
| Vendor Reconciliation Statement Report | `vendor-reconciliation-statement-report.component.ts` | payables dynamic reports API | Dynamic payables filter defaults now use FY start -> effective date, with explicit date inputs driving the report window. |

## As-Of Only

These reports are not opening-vs-movement range reports. They are position reports driven by a
single effective date, so they do not need the separate opening split rule.

| Report | Primary Date Model | Notes |
|---|---|---|
| Vendor Outstanding | `as_of_date` | Already passes FY start and as-of date where needed for payable exposure logic. |
| Accounts Receivable Aging | `as_of_date` | Aging snapshot, not a movement report. |
| Accounts Payable Aging | `as_of_date` | Aging snapshot, not a movement report. |
| MSME Overdue Report | `as_of_date` | Snapshot/exposure style report. |
| Inventory Control Report | `as_of_date` | Inventory operational snapshot. |
| Inventory Stock Aging | `as_of_date` | Inventory aging snapshot. |
| Open Items | `as_of_date` | Now anchored by a selected effective date, with drilldowns carrying that date forward to downstream snapshot reports. |
| Customer Ledger Statement | `as_of_date` | Snapshot statement now honors an explicit effective date while keeping the closed-item toggle separate from date scope. |

## Aligned By Simpler Explicit-Date Model

These reports use explicit `from_date`/`to_date` windows, but they are not opening-balance
financial statement reports. They should still respect effective date windows, though they do not
need the opening/movement split.

| Report | Model | Notes |
|---|---|---|
| Daybook | explicit `from_date`/`to_date` | Needs consistent date-window validation, but not opening logic. |
| Sales Register | explicit `from_date`/`to_date` | Operational register, not opening-balance driven. |
| Purchase Register | explicit `from_date`/`to_date` | Operational register, not opening-balance driven. |
| Stock Ledger Book | explicit `from_date`/`to_date` | Inventory movement report, separate stock rules apply. |
| GRN Invoice Posting Exceptions | explicit `from_date`/`to_date` | Operational exception report. |
| Duplicate / Anomalous Bill Detection | explicit `from_date`/`to_date` | Operational exception report. |
| GST Exception Dashboard | explicit date window or as-of | Tax exception view, not opening-balance driven. |
| Payables Reporting (generic shell) | explicit `from_date`/`to_date` or `as_of_date` depending report | Dynamic report shell; rule depends on underlying report definition. |
| Collections History | explicit `from_date`/`to_date` | History report now follows the same effective date-window contract and forwards end-date snapshots into related drilldowns. |

## Still Needs Work

These screens are the main remaining places where the common reporting scope rule is either not
implemented yet or not expressed through the same scope contract.

| Report | Gap | Recommended Next Step |
|---|---|---|
| Posting Detail | Carries scope context from source reports but is not itself part of the scope contract. | Verify that inherited scope is displayed consistently, but lower priority. |

## Out Of Scope For Opening Logic

These screens were intentionally excluded from the opening/movement audit because they are setup,
hubs, filing packs, dashboards, or operational modules rather than financial balance reports:

- `financial-hub.component.ts`
- `financial-reporting.component.ts`
- `inventory-hub.component.ts`
- `receivables-hub.component.ts`
- `payables-hub.component.ts`
- `year-end-close.component.ts`
- `gstr9report.component.ts`
- `gstr3breport.component.ts`
- `gstreport.component.ts`
- `tcs-filing-pack.component.ts`
- `tcs-ledger-report.component.ts`
- `bank-reconciliation.component.ts`

## Recommended Working Order

1. Posting Detail
2. Daybook / operational explicit-date reports, if we want one shared date-window helper there too

## Verification Status

The following aligned financial statement reports already have focused regression coverage in place:

- Trial Balance
- Ledger Summary
- Ledger Book
- Balance Sheet
- Profit & Loss
- Trading Account
- Cashbook
- Vendor Ledger Statement

This file is an audit snapshot as of `31 May 2026`.
