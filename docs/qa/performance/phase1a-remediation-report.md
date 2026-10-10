# Finacc Phase 1A Remediation Report

Date: 2026-10-10
Scope: Baseline bottleneck remediation, low-volume only

## Evidence

- Purchase Django probe after deferred-field/pagination fix: `docs/qa/performance/evidence/phase1a_purchase_invoices_after_pagination_2026-10-10.json`
- Purchase Gunicorn HTTP probe after fix: `docs/qa/performance/evidence/phase1a_purchase_invoices_gunicorn_after_2026-10-10.json`
- Failed intermediate purchase probe before pagination fix: `docs/qa/performance/evidence/phase1a_purchase_invoices_after_2026-10-10.json`
- Payables attempted optimization measurement: `docs/qa/performance/evidence/phase1a_vendor_outstanding_after_2026-10-10.json`
- Payables current re-probe with no retained code change: `docs/qa/performance/evidence/phase1a_vendor_outstanding_current_2026-10-10.json`
- Payables Phase 1A.3 service probe after summary aggregate: `docs/qa/performance/evidence/phase1a3_vendor_outstanding_after_summary_aggregate_2026-10-10.json`
- Payables Phase 1A.3 Gunicorn probe after summary aggregate: `docs/qa/performance/evidence/phase1a3_vendor_outstanding_gunicorn_after_2026-10-10.json`
- Payables Phase 1A.3 summary aggregate execution plan: `docs/qa/performance/evidence/phase1a3_vendor_outstanding_summary_aggregate_explain_2026-10-10.json`
- Sales/daybook Phase 1A.4/1A.5 before probe: `docs/qa/performance/evidence/phase1a45_sales_daybook_before_2026-10-10.json`
- Sales/daybook Phase 1A.4/1A.5 first after probe: `docs/qa/performance/evidence/phase1a45_sales_daybook_after_2026-10-10.json`
- Daybook Phase 1A.5 final after probe: `docs/qa/performance/evidence/phase1a45_daybook_after_2026-10-10.json`
- Sales/daybook Phase 1A.4/1A.5 Gunicorn after probe: `docs/qa/performance/evidence/phase1a45_sales_daybook_gunicorn_after_2026-10-10.json`
- Receivables open-items after projection fix: `docs/qa/performance/evidence/phase1a_receivables_open_items_after_2026-10-10.json`
- Receivables open-items Gunicorn after projection fix: `docs/qa/performance/evidence/phase1a_receivables_open_items_gunicorn_after_2026-10-10.json`
- Locust token-auth smoke: `docs/qa/performance/evidence/locust_phase1a_token_smoke_1u_10s_2026-10-10.html`

## Purchase Invoices Full List

Baseline from Phase 1: endpoint exceeded manual stop threshold. Stack trace showed serializer access to deferred fields triggering repeated `refresh_from_db()`.

Investigation found two issues:

- `PurchaseInvoiceListSerializer` exposed legacy fields that were omitted from the list queryset `.only()` projection.
- `page=1&page_size=25` was ignored by the full-list endpoint, so the baseline request serialized the full scoped result set and returned about 72 MB.

Changes made:

- Added `is_legacy_imported`, `legacy_source_system`, `legacy_source_key`, and `legacy_import_mode` to the purchase list queryset projection.
- Honored explicit `page` and `page_size` query params while preserving the existing array response shape.
- Added targeted tests to protect the list projection and explicit page-size behavior.

Before/after:

| Measurement | Status | Time ms | Queries | SQL ms | Response bytes |
|---|---:|---:|---:|---:|---:|
| Phase 1 baseline | stopped | >120000 | n/a | n/a | n/a |
| After projection only | 200 | 23567.07 | 34 | 432.00 | 72507984 |
| After projection + explicit pagination | 200 | 105.58 | 34 | 69.00 | 25256 |
| Gunicorn HTTP after fix | 200 | 895.09 | n/a | n/a | 25256 |

Tests:

```bash
venv/bin/python manage.py test \
  purchase.tests.PurchaseInvoiceViewUnitTests.test_list_honors_explicit_page_size_without_changing_array_contract \
  purchase.tests.PurchaseInvoiceViewUnitTests.test_list_queryset_projects_all_direct_serializer_model_fields \
  purchase.tests.PurchaseInvoiceViewUnitTests.test_list_queryset_selects_vendor_related_profiles \
  purchase.tests.PurchaseInvoiceViewUnitTests.test_list_queryset_uses_exists_for_line_mode_filter
```

Result: passed.

## Payables Vendor Outstanding

Baseline: 7440.61 ms, 42 queries, 408 ms SQL.

Investigation:

- The endpoint is not primarily DB-bound; SQL time is far below wall time.
- It iterates open-item/advance rows and builds summary metadata in Python before pagination.
- A first optimization attempt to delay vendor-master loading and restrict vendor loading to active IDs was measured and did not improve the endpoint on the local dataset.

Attempted measurement:

| Measurement | Status | Time ms | Queries | SQL ms | Response bytes |
|---|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 7440.61 | 42 | 408.00 | n/a |
| Attempted active-vendor loading | 200 | 8143.20 | 42 | 561.00 | 161793 |

Decision: backed out the attempted payables change. No payables production code change remains from that attempt.

Current re-probe:

| Measurement | Status | Time ms | Queries | SQL ms | Rows | Total rows |
|---|---:|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 7440.61 | 42 | 408.00 | n/a | n/a |
| Current service probe, warm | 200 | 7435.48 | 10 | 375.00 | 100 | 970 |

Financial reconciliation on current probe:

- `outstanding`: `32090147.20`
- `credit_balance`: `715982.00`
- `advance_balance`: `2129939.00`
- `overdue_amount`: `34220086.20`

Phase 1A.3 remediation:

- Added `open_item_vendor_outstanding_summary(...)`, a database-side vendor aggregate for `view=summary`.
- Preserved detailed mode by leaving the existing item-by-item path intact.
- Summary mode now avoids materializing all as-of open items in Python when no voucher-type filter is supplied.
- Preserved opening balances, bills, payments, credit balances, advances, aging buckets, oldest due date, sorting, pagination, drilldowns, trace payloads, tenant scope, and the existing due-on-as-of bucket behavior.
- Voucher-type filtered summary requests still use the legacy path because label matching currently depends on Python-side document display names.

Before/after:

| Measurement | Status | Time ms | Queries | SQL ms | Rows | Total rows | Response bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 7440.61 | 42 | 408.00 | n/a | n/a | n/a |
| Current service probe before Phase 1A.3 | 200 | 7435.48 | 10 | 375.00 | 100 | 970 | n/a |
| After summary aggregate, warm service probe | 200 | 1630.11 | 9 | 275.00 | 100 | 970 | n/a |
| Gunicorn HTTP after summary aggregate | 200 | 1609.10 | n/a | n/a | 100 | 970 | 312602 |

Financial reconciliation after Phase 1A.3:

- `outstanding`: `32090147.20`
- `credit_balance`: `715982.00`
- `advance_balance`: `2129939.00`
- `overdue_amount`: `34220086.20`
- `bucket_0_30`: `24339347.00`
- `bucket_31_60`: `2950757.00`
- `bucket_61_90`: `3252131.20`
- `bucket_91_180`: `3664070.00`
- `bucket_181_plus`: `695.00`

Result: retained. Warm service time improved by about 78% versus the current pre-fix re-probe, and Gunicorn one-shot latency is now about 1.6s on the same local dataset and filters.

Execution plan note:

- The new summary aggregate ran in about `127.89 ms` inside PostgreSQL on the local dataset.
- PostgreSQL used hash aggregation over `purchase_vendorbillopenitem` and `purchase_purchaseinvoiceheader`.
- The plan still shows sequential scans on the local dataset; this is acceptable for the retained change because end-to-end latency improved materially, but larger staging data should be reviewed for a partial/composite index that matches `(entity_id, entityfinid_id, subentity_id, is_open, bill_date)`.

Tests:

```bash
venv/bin/python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_report_builds_vendor_totals_and_drilldowns \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_matches_legacy_item_math_with_stable_query_count \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_reconciliation_warning_flags_difference \
  reports.tests_payables.PayableReportAPITests.test_negative_vendor_balance_is_retained_in_vendor_outstanding \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_aging_basis_bill_date_can_mark_future_due_bill_as_overdue \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_credit_limit_exceeded_filters_to_breached_vendors \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_search_filters_by_vendor_name \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_and_invoice_aging_apply_pagination \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_detailed_include_advances_separately_shows_advance_row \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_detailed_keeps_open_bill_rows_when_vendor_net_is_negative_due_to_advances \
  --keepdb
```

Result: passed, 10 tests.

Remaining payables risks:

- Voucher-type filtered summary uses the legacy Python materialization path.
- Opening balance and advance summaries still use existing selectors; they were not the dominant bottleneck in this dataset.
- Further gains likely require combining period bill totals, opening balances, and advance summaries into fewer SQL aggregates.

## Sales Invoice List

Baseline: 4657.96 ms, 31 queries, 191 ms SQL, 14,734,470 response bytes.

Investigation:

- The benchmark and browser request sent `page=1&page_size=25`, but `SalesInvoiceListCreateAPIView` only honored `limit`/`offset`.
- Because `page/page_size` was ignored, the endpoint serialized 25,901 invoice rows into a 14 MB array.
- SQL was not the bottleneck; Python serialization and response size dominated.

Change made:

- Added explicit `page`/`page_size` parsing to the list view.
- Preserved the existing array response contract.
- Preserved `limit`/`offset` behavior and no-pagination legacy behavior when neither pagination style is supplied.
- Existing lightweight serializer and queryset projection remain unchanged.

Before/after:

| Measurement | Status | Time ms | Queries | SQL ms | Rows | Response bytes |
|---|---:|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 4657.96 | 31 | 191.00 | n/a | 14734470 |
| Current before fix | 200 | 7081.20 | 31 | 161.00 | 25901 | 14734470 |
| After page/page_size fix | 200 | 127.59 | 31 | 62.00 | 25 | 14161 |
| Gunicorn HTTP after fix | 200 | 132.75 | n/a | n/a | 25 | 14161 |

Result: retained. The endpoint now behaves like the purchase list and lookup filters: page-size requests return the requested window while keeping the JSON array contract.

Tests:

```bash
venv/bin/python manage.py test \
  sales.tests.SalesComplianceRecoveryUnitTests.test_list_view_honors_page_size_without_changing_array_contract \
  sales.tests.SalesComplianceRecoveryUnitTests.test_list_view_records_perf_state_when_enabled \
  sales.tests.SalesComplianceRecoveryUnitTests.test_list_view_uses_lightweight_serializer \
  --keepdb
```

Result: passed, 3 tests.

## Financial Daybook

Baseline: 3004.64 ms, 34 queries, 2933 ms SQL.

Investigation:

- Daybook was SQL-bound.
- The queryset always used `DISTINCT` after entry-level grouping, causing expensive count and page queries.
- The page query also annotated debit/credit totals and document metadata before pagination, so PostgreSQL computed voucher totals and source subqueries for the full filtered set even though only 50 rows were returned.

Changes made:

- Removed unnecessary `DISTINCT` from the normal daybook queryset.
- Kept full filtered-set totals separate, as required by the report contract.
- Paginated entry IDs first, then applied debit/credit and source-document annotations only to the visible page rows.
- Preserved filters, sorting, cancellation exclusions, totals, drilldowns, response fields, pagination metadata, and tenant scope.

Before/after:

| Measurement | Status | Time ms | Queries | SQL ms | Rows | Total rows | Debit/Credit total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 3004.64 | 34 | 2933.00 | n/a | n/a | n/a |
| Current before fix | 200 | 4007.43 | 34 | 3924.00 | 50 | 49074 | 245697566.11 |
| After removing DISTINCT only | 200 | 2662.65 | 34 | 2593.00 | 50 | 49074 | 245697566.11 |
| After page-only annotation | 200 | 221.76 | 35 | 150.00 | 50 | 49074 | 245697566.11 |
| Gunicorn HTTP after fix | 200 | 429.20 | n/a | n/a | 50 | 49074 | 245697566.11 |

Result: retained. The same dataset and filters preserved the transaction count and financial totals while reducing local warm service latency by about 94% versus the current pre-fix probe.

Tests:

```bash
venv/bin/python manage.py test \
  reports.tests_books.BookReportAPITests.test_daybook_happy_path_and_summary \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  reports.tests_books.BookReportAPITests.test_daybook_query_count_does_not_grow_with_page_size \
  reports.tests_books.BookReportAPITests.test_daybook_response_contract_and_nullability \
  reports.tests_books.BookReportAPITests.test_daybook_filters_voucher_type_status_posted_and_search \
  reports.tests_books.BookReportAPITests.test_daybook_purchase_rows_use_purchase_invoice_drilldown \
  reports.tests_books.BookReportAPITests.test_daybook_sales_service_rows_expose_service_invoice_route \
  --keepdb
```

Result: passed, 7 tests.

## Receivables Open Items

Baseline: 6833.50 ms, 37 queries, 549 ms SQL.

Investigation:

- The endpoint builds all open-item rows and totals before pagination, which is required to preserve report totals.
- SQL was not the only bottleneck. The largest query selected full `CustomerBillOpenItem`, `Customer`, `Ledger`, `SubEntity`, and `SalesInvoiceHeader` rows even though the response only uses a small set of fields.
- This caused unnecessary database transfer and Django model hydration on the 10,181-row local result set.

Change made:

- Added an explicit `.only(...)` projection to the open-items queryset for the fields used by the response builder: document fields, amount fields, customer ledger/name fields, customer GST/credit/currency fields, header doc type, and subentity name.
- Preserved the response contract, tenant filters, sorting, pagination, credit balances, unapplied receipts, service-invoice route drilldown, and financial totals.
- Added a query-count regression test so row growth does not introduce per-row ORM lookups.

Before/after:

| Measurement | Status | Time ms | Queries | SQL ms | Rows | Total rows | Outstanding |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phase 1 baseline | 200 | 6833.50 | 37 | 549.00 | n/a | n/a | n/a |
| Current before fix, warm | 200 | 6604.14 | 7 | 415.00 | 100 | 10181 | 19508320.13 |
| After projection fix, warm | 200 | 3052.42 | 7 | 263.00 | 100 | 10181 | 19508320.13 |
| Gunicorn HTTP after projection fix | 200 | 3628.65 | n/a | n/a | 100 | 10181 | 19508320.13 |

Result: retained. The same dataset and filters produced identical financial totals and row count, with local warm service time reduced by about 54%.

Tests:

```bash
venv/bin/python manage.py test \
  reports.tests_receivables.ReceivablesRouteContractTests \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_report_builds_vendor_totals_and_drilldowns \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_and_invoice_aging_apply_pagination \
  --keepdb
```

Result: passed, 18 tests.

## Locust Authentication

Change made:

- `perf/locust/locustfile.py` now accepts `FINACC_ACCESS_TOKEN` as a secure environment-only authentication path.
- Existing `FINACC_USER_EMAIL` and `FINACC_USER_PASSWORD` login still works.
- No token or password is stored in the repository or evidence files.

Smoke validation:

```bash
FINACC_ACCESS_TOKEN=<ephemeral-local-token> \
LOCUST_HOST=http://127.0.0.1:8000 \
FINACC_ENTITY_ID=10 \
FINACC_ENTITY_FIN_ID=8 \
FINACC_SUBENTITY_ID=8 \
FINACC_REPORT_AS_OF_DATE=2026-10-10 \
venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 1 --spawn-rate 1 --run-time 10s --tags read-modern
```

Result: passed. `auth/me` returned 0 failures; aggregate smoke had 6 requests and 0 failures. This was an auth smoke only, not load testing.

## Remaining Phase 1A Items

Not yet remediated in this pass:

- Voucher-type filtered payables vendor outstanding summary remains on the legacy Python materialization path.

Phase 1B readiness verdict: locally ready for controlled low-concurrency Phase 1B smoke profiles, but not for high-concurrency certification yet. Before Phase 2, validate these same endpoints on staging-sized data, review the daybook plan for index opportunities, and either remediate or explicitly accept the voucher-type filtered payables summary residual risk.
