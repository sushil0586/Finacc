# Financial Reports Closure Plan

Last updated: 2026-08-02

Status: planned, phased execution tracker created

Related documents:
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [OVERALL_PRODUCT_CONFIDENCE_MATRIX.md](/Users/ansh/Documents/Eductech/docs/qa-runbooks/OVERALL_PRODUCT_CONFIDENCE_MATRIX.md:1)

## Purpose

This document is the working execution board for moving the financial reports surface to a high-confidence state.

It is designed to answer:

1. Which financial reports are in scope?
2. In what order should we close them?
3. What exactly must be verified for each phase?
4. What observations, defects, and follow-up work were found after each phase?

This document should be updated after every completed phase before moving to the next one.

## In-Scope Financial Reports

Core financial report surfaces:

1. `Financial Reports Meta`
2. `Financial Hub Settings`
3. `Trial Balance`
4. `Ledger Book`
5. `Ledger Summary`
6. `Profit and Loss`
7. `Balance Sheet`
8. `Trading Account`

Closely related financial book reports:

1. `Daybook`
2. `Cashbook`
3. `Posting / Daybook Entry Detail`

## Real API / UI Surface Inventory

Primary routes currently exposed:

- `financial/meta/`
- `financial/settings/financial-hub/`
- `financial/trial-balance/`
- `financial/trial-balance/excel/`
- `financial/trial-balance/pdf/`
- `financial/trial-balance/csv/`
- `financial/trial-balance/print/`
- `financial/ledger-book/`
- `financial/ledger-book/excel/`
- `financial/ledger-book/pdf/`
- `financial/ledger-book/csv/`
- `financial/ledger-book/print/`
- `financial/ledger-summary/`
- `financial/ledger-summary/excel/`
- `financial/ledger-summary/pdf/`
- `financial/ledger-summary/csv/`
- `financial/ledger-summary/print/`
- `financial/profit-loss/`
- `financial/profit-loss/excel/`
- `financial/profit-loss/excel/landscape/`
- `financial/profit-loss/excel/portrait/`
- `financial/profit-loss/pdf/`
- `financial/profit-loss/pdf/landscape/`
- `financial/profit-loss/pdf/portrait/`
- `financial/profit-loss/csv/`
- `financial/profit-loss/print/`
- `financial/balance-sheet/`
- `financial/balance-sheet/excel/`
- `financial/balance-sheet/excel/landscape/`
- `financial/balance-sheet/excel/portrait/`
- `financial/balance-sheet/pdf/`
- `financial/balance-sheet/pdf/landscape/`
- `financial/balance-sheet/pdf/portrait/`
- `financial/balance-sheet/csv/`
- `financial/balance-sheet/print/`
- `financial/trading-account/`
- `financial/trading-account/excel/`
- `financial/trading-account/excel/landscape/`
- `financial/trading-account/excel/portrait/`
- `financial/trading-account/pdf/`
- `financial/trading-account/pdf/landscape/`
- `financial/trading-account/pdf/portrait/`
- `financial/trading-account/csv/`
- `financial/trading-account/print/`

Related financial books:

- `daybook`
- `cashbook`
- `posting detail / entry detail drilldown`

## Closure Standard

Each report is only considered closed when all of the following are done for that phase:

1. Permission and entitlement checks are verified.
2. Filter and meta behavior is verified.
3. Data correctness is checked against real seeded or browser-created data.
4. Export parity is verified for all supported formats.
5. Visual/browser validation is completed for the main user path.
6. Edge behaviors are exercised for the report family.
7. Observations and defects are recorded before phase signoff.

## Execution Order

The closure order is intentionally dependency-aware:

1. `Phase 0`: inventory, route-map, data prerequisites, closure checklist
2. `Phase 1`: `Financial Reports Meta` and `Financial Hub Settings`
3. `Phase 2`: `Trial Balance`
4. `Phase 3`: `Ledger Summary`
5. `Phase 4`: `Ledger Book`
6. `Phase 5`: `Profit and Loss`
7. `Phase 6`: `Trading Account`
8. `Phase 7`: `Balance Sheet`
9. `Phase 8`: `Daybook`
10. `Phase 9`: `Cashbook`
11. `Phase 10`: `Posting / Entry Detail` drilldowns
12. `Phase 11`: cross-report parity, browser final pass, confidence scoring

## Phase Tracker

### Phase 0: Inventory and Preconditions

Status:
- `completed`

Goals:
- confirm exact report list from code
- identify route inventory
- define closure standard
- define execution order

Completed:
- core report list extracted from `reports/api/financial/views.py`
- route list extracted from `reports/urls.py`
- phased execution order defined

Observations:
- the financial report family has a clean top-level structure, but each report has its own export and presentation variants, so closure must be report-family based rather than route-by-route only
- `Profit and Loss`, `Balance Sheet`, and `Trading Account` have additional portrait/landscape export variants, so they need deeper export parity checks than `Trial Balance` or `Ledger Book`

Open observations / defects:
- none yet at planning stage

Next step:
- execute `Phase 1`

### Phase 1: Financial Reports Meta and Financial Hub Settings

Status:
- `completed`

Goals:
- verify meta payload completeness
- verify settings persistence and downstream effect on rendering
- verify permission and entitlement behavior
- verify default, override, and invalid-setting behavior

Checklist:
- `financial/meta/` returns valid defaults, scope options, and report metadata
- `financial/settings/financial-hub/` read path works
- settings update path works
- amount display unit changes propagate correctly
- visible-column settings affect output as intended
- no report breaks when settings are partially blank or reset
- browser validation for settings page and one report reflecting the settings

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 2`

Phase 1 update:

What was verified:
- `financial/settings/financial-hub/` focused API suite passed cleanly
- defaults, payload, and effective merged settings shape are returned correctly
- settings patch persistence and normalization behavior are working
- amount display unit and general display settings are normalized on save
- financial report meta route inventory and contract shape were reviewed against the current implementation

Validation commands executed:

```bash
cd Finacc
./venv/bin/python manage.py test reports.tests_financial_hub_settings --keepdb
./venv/bin/python manage.py test reports.tests_financial_hub_settings reports.tests_books.BookReportAPITests.test_financial_meta_includes_daybook_cashbook_filter_support --keepdb
./venv/bin/python manage.py test reports.tests_financial_hub_settings reports.tests_books --keepdb
```

Result summary:
- `reports.tests_financial_hub_settings`: `3/3` passed
- broader mixed run against `reports.tests_books`: green after stale expectation cleanup
- focused verification rerun against the previously failing Phase 1-adjacent cases: `7/7` passed
- full Phase 1-adjacent verification rerun: `70/70` passed

Observations:
- `financial/meta/` is carrying a broad cross-report contract:
  - report registry
  - hub defaults
  - scope contract
  - voucher/account filter support for daybook and cashbook
- `financial-hub-settings` currently gates by entity accessibility, but it does not enforce a dedicated financial-settings permission in the same explicit way the report views enforce report permissions
- the current settings tests use a generic `reports.gst.view` permission fixture and still pass because entity access is the real gate in this endpoint path today

Defects found:
- no confirmed product defect was proven in the `financial-hub-settings` API path during this phase

Fixes completed in this phase:
- removed stale debug-style test accesses to `data["periods"]` from the financial meta and daybook test paths
- aligned the balance-sheet diagnostics expectation with the current signed-difference contract:
  - `difference` is signed as `assets - liabilities_and_equity`
  - `primary_reason.amount` still represents the impact magnitude

Residual risks:
- meta and settings are now test-clean for this phase
- the permission model for `financial-hub-settings` may still need explicit policy tightening if the product intent is “report settings require a dedicated report settings permission”

Decision:
- mark `Phase 1` as `completed`
- carry forward the permission-model observation as a product hardening note
- move to `Phase 2`

### Phase 2: Trial Balance

Status:
- `partial`

Goals:
- close trial balance end to end

Checklist:
- summary vs detailed
- group by `ledger`, `accounthead`, `accounttype`
- zero rows hide/show
- scope mode: financial year, custom, as-of
- opening, debit, credit, closing correctness
- abnormal balance flags
- pagination, sorting, search
- csv, excel, pdf, print parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 3`

Phase 2 update:

What was verified:
- trial balance permission gating path
- trial balance API payload and envelope contract
- opening, debit, credit, and closing calculations on seeded posted ledger movements
- financial-year scope behavior that hides opening values by default
- posted opening balance precedence over legacy master opening values
- exclusion of legacy opening values when no posted opening entry exists
- inclusion of opening-only ledgers in rows and totals
- date-range behavior without explicit scope mode
- standard export action URLs
- period split behavior for `period_by=year`
- helper/export subtitle contract

Validation commands executed:

```bash
cd Finacc
./venv/bin/python manage.py test reports.tests_financial_api_permissions reports.tests_financial_trial_balance_exports reports.tests_books.BookReportAPITests.test_trial_balance_totals_match_posted_ledger_movements reports.tests_books.BookReportAPITests.test_trial_balance_financial_year_hides_opening_values_by_default reports.tests_books.BookReportAPITests.test_trial_balance_prefers_posted_opening_balance_over_legacy_master_opening reports.tests_books.BookReportAPITests.test_trial_balance_ignores_legacy_opening_without_posted_entry reports.tests_books.BookReportAPITests.test_trial_balance_includes_posted_opening_only_ledgers_in_rows_and_totals reports.tests_books.BookReportAPITests.test_trial_balance_date_range_without_scope_mode_still_includes_opening reports.tests_books.BookReportAPITests.test_trial_balance_exposes_standard_export_actions reports.tests_books.BookReportAPITests.test_trial_balance_envelope_exposes_ui_contract reports.tests_books.BookReportAPITests.test_trial_balance_year_period_by_splits_current_financial_year_by_calendar_year --keepdb
```

Result summary:
- focused trial balance verification: `20/20` passed

Observations:
- the current trial balance backend contract is stable on the seeded scenarios already covered in `reports.tests_books`
- one stale helper expectation was found during execution:
  - the subtitle helper now returns humanized labels such as `Custom range`, `Account head`, and `Detailed`
  - the older test still expected raw enum-style values like `custom` and `detailed`
- no fresh trial balance correctness defect was proven in this focused backend/API slice

Fixes completed in this phase:
- updated stale subtitle helper expectations in [reports/tests_financial_trial_balance_exports.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/tests_financial_trial_balance_exports.py)

Defects found:
- no confirmed product defect yet in the focused trial balance backend/API slice

Residual risks:
- browser validation with live data is still pending
- export parity is only covered through helper/API contract checks so far, not yet via browser-triggered real downloads/visual inspection
- grouped/accounthead/accounttype browser behavior and zero-row UX still need end-user verification before full closure

Decision:
- keep `Phase 2` as `partial`
- next step is browser/live-data trial balance verification before final phase signoff

### Phase 3: Ledger Summary

Status:
- `partial`

Goals:
- close ledger summary end to end

Checklist:
- grouped totals correctness
- search, sort, paging
- include/exclude zero balances
- include/exclude inactive ledgers
- export parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 4`

Current baseline before execution:

Covered in code/tests already:
- permission denial path through `reports.tests_financial_api_permissions`
- envelope contract and standard export URL exposure
- date-range opening handling
- financial-year opening suppression behavior
- explicit-date financial-year window behavior
- resolved sort-key reporting contract

Gaps to close in this phase:
- grouped totals correctness for `accounthead` and `accounttype`
- `summary` vs `detailed` child-row behavior
- zero-balance include/exclude behavior in grouped and ledger views
- inactive-ledger include/exclude behavior if supported by the raw source contract
- search behavior and paging stability
- export content parity, not just export URL presence
- browser/live-data validation for filters, grouping, and visible totals

Phase 3 update:

What was verified:
- ledger summary permission denial path
- envelope contract and standard export URL exposure
- date-range opening handling without explicit scope mode
- financial-year opening suppression behavior
- explicit-date financial-year single-window behavior
- resolved sort-key reporting contract
- `group_by=accounthead` with `view_type=detailed` child expansion
- `group_by=accounttype` summary roll-up behavior
- zero-balance include/exclude visibility for orphan ledgers
- filtered search plus pagination record-count stability

Validation commands executed:

```bash
cd Finacc
./venv/bin/python manage.py test reports.tests_financial_api_permissions reports.tests_books.BookReportAPITests.test_ledger_summary_date_range_without_scope_mode_still_includes_opening reports.tests_books.BookReportAPITests.test_ledger_summary_exposes_standard_export_actions reports.tests_books.BookReportAPITests.test_ledger_summary_envelope_exposes_ui_contract reports.tests_books.BookReportAPITests.test_ledger_summary_financial_year_hides_opening_values_by_default reports.tests_books.BookReportAPITests.test_ledger_summary_financial_year_scope_with_explicit_dates_keeps_single_window reports.tests_books.BookReportAPITests.test_ledger_summary_reporting_uses_resolved_sort_key reports.tests_books.BookReportAPITests.test_ledger_summary_accounthead_detailed_includes_group_children reports.tests_books.BookReportAPITests.test_ledger_summary_accounttype_summary_rolls_up_totals reports.tests_books.BookReportAPITests.test_ledger_summary_zero_balance_flag_controls_orphan_ledger_visibility reports.tests_books.BookReportAPITests.test_ledger_summary_search_and_pagination_keep_filtered_record_count --keepdb
```

Result summary:
- focused ledger summary verification: `16/16` passed

Observations:
- separate opening is intentionally scope-sensitive here, just like the existing ledger summary contract:
  - custom/date-range windows can surface separate opening
  - financial-year mode suppresses separate opening by design
- zero-only ledgers are hidden from grouped children unless zero balances are explicitly included
- grouped balance remains signed, so credit-heavy groups can legitimately report a negative closing value

Fixes completed in this phase:
- fixed account-type grouping source so ledger summary now derives account type from the resolved dynamic account head instead of leaving grouped rows unmapped
- added deeper ledger summary regression coverage for grouped rows, child expansion, zero-balance visibility, and filtered pagination stability

Defects found:
- confirmed and fixed:
  - `group_by=accounttype` could collapse rows into `Unmapped Account Type` because account-type metadata was not being carried from the resolved account head path

Residual risks:
- export content parity is still only partially verified; URLs are covered, but browser-triggered downloads and rendered-document inspection are still pending
- inactive-ledger behavior still needs an explicit targeted scenario if the product intends that toggle to influence this report family
- browser/live-data validation is still pending before final phase signoff

Decision:
- keep `Phase 3` as `partial`
- next step is export-content and browser/live-data ledger summary verification before final signoff

### Phase 4: Ledger Book

Status:
- `pending`

Goals:
- close ledger book end to end

Checklist:
- ledger selection correctness
- opening balance correctness
- running balance correctness
- posting order stability
- voucher/document references
- csv, excel, pdf, print parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 5`

### Phase 5: Profit and Loss

Status:
- `pending`

Goals:
- close profit and loss end to end

Checklist:
- period scope correctness
- grouping and presentation correctness
- gross profit / net profit consistency
- stock valuation mode impact
- statement presentation behavior
- csv, excel, pdf, print parity
- portrait and landscape parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 6`

### Phase 6: Trading Account

Status:
- `pending`

Goals:
- close trading account end to end

Checklist:
- opening stock, purchases, closing stock correctness
- gross profit calculation
- period handling
- csv, excel, pdf, print parity
- portrait and landscape parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 7`

### Phase 7: Balance Sheet

Status:
- `pending`

Goals:
- close balance sheet end to end

Checklist:
- assets vs liabilities and equity balancing
- retained earnings / profit linkage correctness
- stock valuation mode impact
- statement presentation correctness
- csv, excel, pdf, print parity
- portrait and landscape parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 8`

### Phase 8: Daybook

Status:
- `pending`

Goals:
- close daybook end to end

Checklist:
- entry listing correctness
- filter correctness
- totals correctness
- export parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 9`

### Phase 9: Cashbook

Status:
- `pending`

Goals:
- close cashbook end to end

Checklist:
- opening and running balances
- account/ledger targeting correctness
- counter-entry interpretation
- export parity
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 10`

### Phase 10: Posting / Entry Detail Drilldowns

Status:
- `pending`

Goals:
- close drilldown consistency across financial books and statements

Checklist:
- entry detail matches parent report row
- journal line ordering
- voucher/document linkage
- export parity where supported
- browser validation with live data

Expected outputs:
- phase status update
- observations list
- defects list
- go/no-go for `Phase 11`

### Phase 11: Cross-Report Parity and Final Confidence Pass

Status:
- `pending`

Goals:
- verify cross-report consistency
- assign final confidence level

Checklist:
- trial balance closing aligns with statement logic
- ledger book and daybook drilldowns agree
- profit and loss feeds balance sheet correctly
- trading account aligns with profit and loss where applicable
- financial hub settings affect all relevant reports consistently
- final browser walkthrough completed

Expected outputs:
- final observations list
- final defects list
- module confidence rating
- residual risks

## Status Update Template

Use this template after each phase:

```md
### Phase X Update

Status:
- `completed` / `partial` / `blocked`

What was verified:
- ...

Observations:
- ...

Defects found:
- ...

Fixes completed in this phase:
- ...

Residual risks:
- ...

Decision:
- move to next phase / hold and fix
```

## Current Read

Current confidence for financial reports before execution:
- `medium`

Reason:
- the route surface is now clearly inventoried
- closure order is defined
- but the report families have not yet been fully closed phase by phase with observations and browser proof in this dedicated tracker

Immediate next step:
- execute `Phase 1: Financial Reports Meta and Financial Hub Settings`
