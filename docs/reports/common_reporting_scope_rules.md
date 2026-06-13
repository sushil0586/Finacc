# Common Reporting Scope Rules

## Purpose

This document defines one shared rule set for how financial reports must interpret:

- period and date filters
- anchor date
- smart filters
- opening, movement, and closing balances
- posted-only and zero-balance behavior

The goal is to remove report-by-report interpretation differences. The same request intent should produce the same balance logic across:

- Trial Balance
- Ledger Summary
- Ledger Book
- Cashbook
- Vendor Ledger Statement
- Balance Sheet
- related financial books and summaries where the same scope concepts apply

## Source Of Truth

All balances must come from `posting_journalline`.

Do not compute reporting balances from ledger master opening fields such as:

- `ledger.openingbdr`
- `ledger.openingbcr`

Opening balances must exist as posted `OPENING_BALANCE` journal lines with a proper counter-entry.

## Core Balance Rule

Whenever a report has an effective start date and end date:

- `Opening` = net posted balance before the effective start date
- `Movement Debit/Credit` = posted movement between the effective start date and effective end date, inclusive
- `Closing` = `Opening + Movement`

Important:

- the `effective start date` itself belongs to `Movement`
- `Opening` therefore runs only up to `effective start date - 1 day`
- all balances remain sourced from posted journal lines only

This rule applies:

- per ledger
- per grouped bucket
- for grand totals

## Canonical Evaluation Model

Every report should resolve filters in this order:

1. Identify scope context:
   - `entity`
   - `entityfinid`
   - `subentity`
2. Resolve the effective date window:
   - `effective_from`
   - `effective_to`
3. Resolve dataset policy:
   - `posted_only`
   - `include_zero_balances`
   - report-specific filters such as ledger, voucher type, search
4. Compute balances:
   - opening before `effective_from`
   - movement inside `effective_from..effective_to`
   - closing as of `effective_to`
5. Apply presentation rules:
   - whether opening is shown as a separate column or row
   - whether rows are grouped or detailed

Important:

- `scope_mode`, `anchor_date`, and smart-filter labels are user-intent inputs
- `effective_from` and `effective_to` are the accounting dates used for actual balance calculation

## Filter Precedence

Use this precedence order consistently across frontend and backend:

1. Explicit `as_of_date`
2. Explicit `from_date` and `to_date`
3. Relative scope plus `anchor_date`
4. Financial-year default window from `entityfinid`

Rules:

- if `as_of_date` is present, treat it as a position report ending on that date
- if `from_date` and `to_date` are present, they define the effective date window even if `scope_mode` is missing
- if a relative scope is selected, derive explicit dates from `anchor_date`
- if no explicit dates are present, use the financial-year start through anchor-date window for the selected `entityfinid`

## Scope Rules

### `financial_year`

Meaning:

- financial year to anchor date

Effective dates:

- `effective_from = fy_start`
- `effective_to = anchor_date`

Anchor date:

- required as the effective end date

Opening presentation:

- if the report is anchor-only, separate opening is usually not required
- if the report is explicit-range, opening means balance before the explicit start date
- no report should include transactions after the anchor date

Recommended label:

- `Financial year`
- operational meaning: `FY to date`

### `month`

Meaning:

- anchor-only view with a month label

Effective dates:

- `effective_from = selected financial year start`
- `effective_to = anchor_date`

Anchor date:

- mandatory for correct resolution

Opening presentation:

- separate opening is not required in anchor-only mode
- if a report exposes separate opening for an explicit date range, opening still means balance before the explicit start date

Recommended label:

- `This month`

### `quarter`

Meaning:

- anchor-only view with a quarter label

Effective dates:

- `effective_from = selected financial year start`
- `effective_to = anchor_date`

Opening presentation:

- separate opening is not required in anchor-only mode
- if a report exposes separate opening for an explicit date range, opening still means balance before the explicit start date

Recommended label:

- `This quarter`

### `year`

Meaning:

- financial year-to-anchor, not calendar year unless a report explicitly documents otherwise

Effective dates:

- `effective_from = selected financial year start`
- `effective_to = anchor_date`

Opening presentation:

- separate opening is not required in anchor-only mode
- if a report exposes separate opening for an explicit date range, opening still means balance before the explicit start date

Recommended label:

- `This year`
- operational meaning: `FY to date`

### `custom`

Meaning:

- exact user-specified range

Effective dates:

- `effective_from = from_date`
- `effective_to = to_date`

Opening presentation:

- opening = all posted balance from financial-year start through the day before `from_date`
- `from_date` itself belongs to movement

### `as_of`

Meaning:

- position as of a single date

Effective dates:

- `effective_from = null for movement presentation`
- `effective_to = as_of_date`

Reporting behavior:

- use all posted entries up to `as_of_date`
- show balance position as of that date

Opening presentation:

- usually not needed as a separate presentation concept
- if a report still exposes opening for structural reasons, it must be clearly documented

## Anchor Date Rule

Anchor date must never allow future data beyond the chosen anchor.

For anchor-only scopes:

- `financial_year` ends on anchor date
- `month` ends on anchor date
- `quarter` ends on anchor date
- `year` ends on anchor date

Example:

- selected scope: `This year`
- anchor date: `30 Apr 2026`
- selected FY: `FY 2026-27`
- effective window must be `01 Apr 2026 to 30 Apr 2026`

It must not return May data.

The same anchor rule applies even if the UI label says `Financial year`, `This month`, or `This quarter`.

## Smart Filter Contract

Smart Filter must resolve into the same canonical filter model as manual filters.

### Scope Filters

Supported scope intents:

- Financial year
- This month
- This quarter
- This year
- Custom range
- As of date

Smart Filter must resolve them into:

- `scope_mode`
- `anchor_date` where applicable
- or explicit `from_date` / `to_date`
- or `as_of_date`

### Entity Context Filters

Supported:

- entity`
- financial year
- branch or subentity

Rules:

- if a financial report depends on FY boundaries, `entityfinid` must be carried through
- custom range and relative scopes must not silently drop `entityfinid`

### Balance And Dataset Filters

Supported:

- posted only
- include zero balances
- include opening
- include movement
- include closing

Rules:

- `posted_only=true` means only posted journal lines affect all balances, including opening
- `include_zero_balances=false` hides rows whose opening, movement, and closing are all zero
- `include_opening`, `include_movement`, and `include_closing` are presentation toggles unless a report explicitly documents otherwise

### Grouping And View Filters

Supported:

- group by ledger
- group by account head
- group by account type
- summary view
- detailed view
- period by month, quarter, year

Rules:

- grouping must not change the underlying balance math
- periodization must apply the same opening-before-start rule for every generated bucket

### Search Filters

Supported:

- ledger name
- account head
- account type
- voucher number
- voucher type
- description

Rules:

- search filters narrow visible rows
- search must not change how opening, movement, and closing are computed for the included row

## Report-Specific Rules

### Trial Balance

- for any explicit date range, show separate `Opening`, `Debit`, `Credit`, `Closing`
- for `as_of`, show position as of date
- opening totals must use balanced side totals, not signed net collapse

### Ledger Summary

- same accounting rule as trial balance
- grouped presentation may differ, balance logic may not
- opening summary card must reflect the same carried-forward opening shown in row openings

### Ledger Book

- if a report has a start date after the natural opening point, show a brought-forward opening row or opening card
- transaction rows must contain only in-range movement
- running balance must start from the carried-forward opening

### Cashbook And Vendor Ledger Statement

- same as ledger book
- separate opening row is valid where the report is inherently movement-ledger style

### Balance Sheet

- position report as of `effective_to`
- posted opening entries are naturally included through journal history
- posted opening must never be double-counted as both opening and movement

## Totals Rule

For reports that show opening and closing as debit/credit balances:

- do not net all row openings into one signed value and display zero when debit and credit sides balance
- compute:
  - opening debit total
  - opening credit total
  - closing debit total
  - closing credit total

If a report exposes only one headline opening figure, it must use the report’s documented convention consistently and not hide real row openings.

## API Contract Rule

For report APIs:

- if `from_date` and `to_date` are present, backend must treat the request as a date-range request even if `scope_mode` is omitted
- if `as_of_date` is present, backend must treat it as a position request even if `scope_mode` is omitted
- `entityfinid` should be preserved whenever FY boundaries are relevant to opening resolution

## Frontend Contract Rule

For report screens:

- frontend must not null out `entityfinid` for custom or relative scopes
- frontend must not assume opening is only for `scope_mode=custom`
- if the UI derives a date range from anchor date, the derived `from_date` and `to_date` must match backend expectations exactly

## Examples

### Example 1: Trial Balance, Custom Range

Inputs:

- `entityfinid = FY 2026-27`
- `from_date = 2026-04-30`
- `to_date = 2026-05-31`

Result:

- opening = all posted balance before `2026-04-30`
- debit and credit = movement from `2026-04-30` to `2026-05-31`
- closing = opening plus movement

### Example 2: Ledger Summary, This Year

Inputs:

- `scope_mode = year`
- `anchor_date = 2026-04-30`
- `entityfinid = FY 2026-27`

Resolved dates:

- `effective_from = 2026-04-01`
- `effective_to = 2026-04-30`

Result:

- no May movement may appear

### Example 3: Ledger Book, As Of Date

Inputs:

- `as_of_date = 2026-05-31`

Result:

- rows included only up to `2026-05-31`
- if presented as movement ledger, the report must document whether it is showing full history-to-date or only the nearest reporting window

## Current Implementation Goal

Before further report changes, each relevant report should be checked against this matrix:

- financial year
- month with anchor
- quarter with anchor
- year with anchor
- custom range
- as-of date
- date range without explicit `scope_mode`
- posted only on and off
- include zero balances on and off
- summary and detailed views

## Approval Note

This document is the proposed common rule set to align frontend and backend behavior.

If product and finance approve this contract, implementation should then be completed report by report using this document as the source of truth.
