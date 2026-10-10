# Finacc Phase 1C Heavy Accounting Report Remediation

Date: 2026-10-10

Environment: local isolated Finacc database, Gunicorn on `127.0.0.1:8021`, 3 sync workers, timeout 120 seconds. Locust authentication used the secure local token environment file; no token values are recorded here. Write and lifecycle tests were disabled.

## Scope

Phase 1C focused on the Phase 1B blocking read-report endpoints:

| Endpoint | Phase 1B symptom |
| --- | ---: |
| Receivables aging invoice report | about 8.2s average, about 9.5s p95/max under 5 users |
| Voucher-type filtered payables vendor outstanding summary | about 7.5s at 1 user |
| Receivables open-items | about 3.0-3.5s under 5 users |

No production services, payment providers, or live GST endpoints were used.

## Bottleneck Findings

Receivables aging invoice and open-items had low SQL query counts, but high Python processing cost. The expensive work was model materialization, related-object traversal, and route-map preparation for the full filtered result set before pagination. SQL time was not the dominant cost.

Voucher-type filtered payables summary had two problems: it used the legacy Python row-scan path and the `PINV` filter did not map to the purchase invoice `doc_type`, so the old path could scan tens of thousands of rows and still return an empty summary.

## Remediation

Receivables:
- Added projected open-item value loading for aging invoice mode.
- Preserved full totals before pagination.
- Moved invoice route-map resolution to the paged rows only.
- Reworked open-items to use projected values plus one bulk customer map instead of materializing full open-item/header/customer objects.

Payables:
- Added database-side vendor outstanding summary aggregation with optional purchase `doc_type` filtering.
- Mapped voucher filters such as `PINV`, `PCN`, and `PDN` to purchase invoice document types.
- Preserved drilldown mode by only using the aggregate path for summary mode.

## Direct Benchmarks

Same local dataset, same entity/FY/subentity/as-of scope.

| Endpoint | Before | After | Queries | Financial result |
| --- | ---: | ---: | ---: | --- |
| Receivables aging invoice | 7002.7 ms | 1639-1676 ms | 8 -> 8 | Totals unchanged |
| Receivables open-items | 3075.7 ms | 1360 ms | 8 -> 8 | Totals unchanged |
| Payables summary, `voucher_type=PINV` | 7567.2 ms | 899-1068 ms | 10 -> 9 | Correctly returns PINV rows instead of incorrect empty result |

Golden reconciliation snapshots:
- Receivables aging invoice balance stayed `19,354,248.13`.
- Receivables open-items totals stayed original `19,624,631.00`, settled `116,310.87`, outstanding `19,508,320.13`.
- Payables `PINV` summary now returns invoice-only balances: net outstanding `31,465,440.00`, bill amount `38,628,034.20`, payments `3,385,178.00`.

## Regression Tests

Executed:

```bash
venv/bin/python -m py_compile reports/services/receivables.py reports/services/payables.py reports/selectors/payables.py

venv/bin/python manage.py test \
  reports.tests_receivables \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_matches_legacy_item_math_with_stable_query_count \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_and_invoice_aging_apply_pagination \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_search_filters_by_vendor_name \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_and_ap_aging_respect_vendor_group_region_currency_scope \
  --keepdb

venv/bin/python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_voucher_type_uses_filtered_aggregate \
  reports.tests_receivables \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_matches_legacy_item_math_with_stable_query_count \
  --keepdb
```

Results: all targeted tests passed. The new payables test proves `voucher_type=["PINV"]` excludes a credit note, preserves invoice outstanding `600.00`, and stays within the query-count guard.

## Phase 1B Retest

### 1 User, 3 Minutes

| Endpoint | Requests | Avg | p50 | p95 | p99 | Max | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aggregate | 81 | 425 ms | 130 ms | 1500 ms | 2000 ms | 1980 ms | 0 |
| Receivables aging invoice | 1 | 1694 ms | 1700 ms | 1700 ms | 1700 ms | 1694 ms | 0 |
| Receivables aging summary | 7 | 1557 ms | 1500 ms | 2000 ms | 2000 ms | 1980 ms | 0 |
| Payables vendor outstanding summary | 4 | 1085 ms | 1100 ms | 1200 ms | 1200 ms | 1155 ms | 0 |

### 5 Users, 5 Minutes

| Endpoint | Requests | Avg | p50 | p95 | p99 | Max | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aggregate | 630 | 402 ms | 120 ms | 1500 ms | 1800 ms | 2362 ms | 0 |
| Receivables aging invoice | 16 | 1786 ms | 1800 ms | 2000 ms | 2000 ms | 1957 ms | 0 |
| Receivables aging summary | 40 | 1483 ms | 1400 ms | 2100 ms | 2400 ms | 2362 ms | 0 |
| Receivables open-items | 21 | 1511 ms | 1500 ms | 1700 ms | 1700 ms | 1680 ms | 0 |
| Payables vendor outstanding summary | 34 | 1079 ms | 1100 ms | 1200 ms | 1400 ms | 1411 ms | 0 |
| Financial daybook | 25 | 293 ms | 250 ms | 480 ms | 520 ms | 515 ms | 0 |

The 5-user gate passed, so the bounded 10-user read-only profile was attempted.

### 10 Users, 10 Minutes

| Endpoint | Requests | Avg | p50 | p95 | p99 | Max | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aggregate | 2496 | 428 ms | 130 ms | 1600 ms | 2400 ms | 2977 ms | 0 |
| Receivables aging invoice | 56 | 1990 ms | 1900 ms | 2700 ms | 2700 ms | 2732 ms | 0 |
| Receivables aging summary | 132 | 1582 ms | 1500 ms | 2400 ms | 2800 ms | 2861 ms | 0 |
| Receivables open-items | 82 | 1680 ms | 1500 ms | 2600 ms | 3000 ms | 2977 ms | 0 |
| Payables vendor outstanding summary | 120 | 1183 ms | 1100 ms | 1700 ms | 2500 ms | 2955 ms | 0 |
| Financial daybook | 134 | 322 ms | 250 ms | 730 ms | 1300 ms | 2195 ms | 0 |

## Evidence

- `docs/qa/performance/evidence/phase1c_locust_summary_2026-10-10.json`
- `docs/qa/performance/evidence/locust_phase1c_mixed_1u_3m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/locust_phase1c_mixed_1u_3m_2026-10-10.html`
- `docs/qa/performance/evidence/locust_phase1c_mixed_5u_5m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/locust_phase1c_mixed_5u_5m_2026-10-10.html`
- `docs/qa/performance/evidence/locust_phase1c_mixed_10u_10m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/locust_phase1c_mixed_10u_10m_2026-10-10.html`

## Remaining Risks

- This was local certification only; it must not be used as a production capacity claim.
- Resource telemetry still needs a more reliable process RSS, PostgreSQL wait-event, lock, and slow-query sampler.
- Write/concurrency financial integrity was not re-certified in this Phase 1C read-heavy run.
- Receivables reports still carry large response payloads, so staging should validate network transfer and browser rendering under realistic data volumes.

## Verdict

Phase 1B retest after Phase 1C remediation: Pass for controlled local read-heavy 1-user, 5-user, and bounded 10-user profiles.

Phase 2 readiness: Conditional. The former P0 read-report blockers are remediated enough for staging-style controlled load preparation, but Phase 2 should wait for reliable resource telemetry and disposable write-concurrency financial integrity checks.
