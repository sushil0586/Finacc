# Finacc Phase 1B Local Load Report

Date: 2026-10-10  
Environment: local isolated Finacc development database and local Gunicorn app server  
Verdict: Conditional

## Scope

Phase 1B covered controlled local API load only. It did not certify production capacity, and it did not run high-concurrency tests after local results showed long-tail latency at 5 users.

The exercised workload used the reusable Locust framework under `perf/locust/` with realistic read-heavy accounting workflows across sales, purchase, receivables, payables, and financial reports. Response validation checked JSON shape and required business fields rather than only HTTP status codes.

Write/concurrency financial integrity tests were not enabled for this local database. Invoice creation, voucher numbering, duplicate request handling, payment allocation, and ledger consistency still require disposable fixtures or a staging-like database before Phase 2.

## Readiness Checks

| Check | Result | Evidence |
| --- | --- | --- |
| Isolated local database | Pass | Local `.env` points to local PostgreSQL database `finacc_db` on `127.0.0.1`. No production host was used. |
| Valid token authentication | Pass | Auth smoke against Gunicorn returned HTTP 200 for the isolated test user. Token value was kept outside committed files. |
| Production representative app server | Pass | Gunicorn 23.0.0, sync worker class, 3 workers, 120 second timeout, bound to `127.0.0.1:8021`. Django runserver was not used for load runs. |
| Actual API routes | Pass | Locust used real Finacc API routes from the existing Phase 1/1A harness. |
| External provider safety | Pass | GST provider, payment provider, and destructive write workflows were excluded. `FINACC_ENABLE_WRITE_TESTS=false` and lifecycle tests were disabled. |
| Response validation | Pass | Locust validators were added for list, report, object, and selected accounting payload fields. |
| Resource capture | Partial | CPU, load average, and PostgreSQL connection counts were captured. RAM/RSS capture was unreliable because the monitor did not consistently resolve worker RSS. |

## Executed Runs

Earlier smoke attempts with invalid credentials or overly strict harness validation are retained as evidence but excluded from certification results. The official Phase 1B result set starts with the corrected `_r5` 1-user run.

| Run | Users | Duration | Requests | Failures | RPS | p50 | p95 | p99 | Max | Avg response size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `locust_phase1b_mixed_1u_3m_2026-10-10_r5` | 1 | 3 min | 71 | 0 | 0.398 | 140 ms | 2,000 ms | 7,500 ms | 7,458 ms | 302,930 bytes |
| `locust_phase1b_mixed_5u_5m_2026-10-10` | 5 | 5 min | 598 | 0 | 1.997 | 110 ms | 2,800 ms | 8,000 ms | 9,482 ms | 228,608 bytes |
| `locust_phase1b_payables_voucher_filter_1u_2m_2026-10-10` | 1 | 2 min | 13 | 0 | 0.108 | 7,400 ms | 7,900 ms | 7,900 ms | 7,875 ms | 0 bytes for CSV aggregate row |

## Per-Endpoint Findings

### Mixed 1-User Run

| Endpoint | Count | Average | p95 | Max | Finding |
| --- | ---: | ---: | ---: | ---: | --- |
| `reports/receivables/aging [invoice]` | 2 | 7,316 ms | 7,500 ms | 7,458 ms | Critical long-tail bottleneck. |
| `reports/receivables/open-items [get]` | 1 | 2,916 ms | 2,900 ms | 2,916 ms | Still heavy after Phase 1A. |
| `reports/receivables/aging [summary]` | 3 | 1,652 ms | 2,000 ms | 2,000 ms | Moderate report bottleneck. |
| `reports/payables/vendor-outstanding [summary]` | 6 | 1,168 ms | 1,400 ms | 1,425 ms | Phase 1A summary optimization holds for unfiltered summary. |
| `reports/financial/daybook [get]` | 3 | 468 ms | 480 ms | 478 ms | Acceptable locally at 1 user. |

### Mixed 5-User Run

| Endpoint | Count | Average | p95 | Max | Finding |
| --- | ---: | ---: | ---: | ---: | --- |
| `reports/receivables/aging [invoice]` | 10 | 8,205 ms | 9,500 ms | 9,482 ms | Blocks Phase 2 readiness. |
| `reports/receivables/open-items [get]` | 22 | 3,027 ms | 3,500 ms | 3,551 ms | Too slow under light concurrency. |
| `reports/receivables/aging [summary]` | 35 | 1,655 ms | 2,800 ms | 3,264 ms | Needs further query/aggregation review. |
| `reports/payables/vendor-outstanding [summary]` | 32 | 1,185 ms | 1,500 ms | 1,782 ms | Stable enough for current local read profile. |
| `reports/financial/daybook [get]` | 32 | 305 ms | 470 ms | 717 ms | Phase 1A remediation remains effective. |

Sales and purchase lookup/list workflows stayed mostly under sub-second p95 during the valid mixed runs. Pagination behavior remained stable in the sampled workload.

### Voucher-Type Filtered Payables Summary

The residual-risk run confirms the known Phase 1A limitation:

| Endpoint | Count | Average | p95 | Max | Finding |
| --- | ---: | ---: | ---: | ---: | --- |
| `reports/payables/vendor-outstanding [summary voucher=PINV]` | 12 | 7,457 ms | 7,900 ms | 7,875 ms | Still using the legacy slow path. Must be remediated before Phase 2. |

## Resource Observations

| Run | Max load1 | Max CPU user | Max CPU sys | Max PostgreSQL connections | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 user mixed | 4.59 | 29.96% | 18.26% | 4 | Long-tail latency is endpoint-bound, not caused by high user count. |
| 5 user mixed | 4.78 | 40.51% | 17.42% | 4 | Three sync Gunicorn workers can be occupied by slow report calls. |
| 1 user voucher filter | 4.51 | 25.00% | 21.90% | 2 | Single slow endpoint remains expensive without concurrency. |

RAM/RSS values from the local monitor are not reliable and should be fixed before repeating Phase 1B or running staging certification.

## Regression Results

Post-load deterministic regression command:

```bash
venv/bin/python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_report_builds_vendor_totals_and_drilldowns \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_matches_legacy_item_math_with_stable_query_count \
  reports.tests_receivables.ReceivablesRouteContractTests \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  reports.tests_books.BookReportAPITests.test_daybook_query_count_does_not_grow_with_page_size \
  sales.tests.SalesComplianceRecoveryUnitTests.test_list_view_honors_page_size_without_changing_array_contract \
  --keepdb
```

Result: 21 tests passed.

These tests cover the Phase 1A financial/report contract areas that were touched previously. They do not replace write-concurrency accounting certification.

## Bottlenecks

P0:
- Receivables aging invoice report averages about 8.2 seconds at 5 local users and reaches about 9.5 seconds p95/max. This blocks Phase 2 readiness.
- Voucher-type filtered payables summary remains about 7.5 seconds at a single user because it still follows the legacy implementation.

P1:
- Receivables open-items remains about 3.0 to 3.5 seconds under 5 users.
- Three sync Gunicorn workers are easy to occupy with slow report requests, which can delay otherwise fast endpoints.
- Several report responses are large enough to make serialization and transfer cost material.

P2:
- Local resource monitor needs reliable RAM/RSS and PostgreSQL wait/slow-query snapshots.
- Concurrent write financial checks need disposable/staging fixtures before certification can proceed.

## Stopped Load Escalation

The planned 10, 25, and 50 user runs were not executed. This was intentional: the 5-user run had zero request failures, but p99 reached about 8 seconds and p99.9 reached about 9.5 seconds. Escalating load would mostly prove worker saturation around already-known report bottlenecks.

## Evidence

Primary evidence:
- `docs/qa/performance/evidence/locust_phase1b_mixed_1u_3m_2026-10-10_r5_stats.csv`
- `docs/qa/performance/evidence/locust_phase1b_mixed_1u_3m_2026-10-10_r5_stats_history.csv`
- `docs/qa/performance/evidence/locust_phase1b_mixed_1u_3m_2026-10-10_r5_resources.csv`
- `docs/qa/performance/evidence/locust_phase1b_mixed_5u_5m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/locust_phase1b_mixed_5u_5m_2026-10-10_stats_history.csv`
- `docs/qa/performance/evidence/locust_phase1b_mixed_5u_5m_2026-10-10_resources.csv`
- `docs/qa/performance/evidence/locust_phase1b_payables_voucher_filter_1u_2m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/locust_phase1b_payables_voucher_filter_1u_2m_2026-10-10_resources.csv`
- `docs/qa/performance/evidence/phase1b_summary_2026-10-10.json`

Excluded harness/auth attempts are also preserved in the evidence folder for traceability, but they are not counted as certification results.

## Phase 2 Readiness

Phase 1B status: Conditional.

Phase 2 readiness recommendation: Not ready for high-concurrency load testing yet.

Before Phase 2:
1. Optimize receivables aging invoice and summary report paths.
2. Remediate voucher-type filtered payables summary without changing financial rules.
3. Re-run 1-user and 5-user Phase 1B profiles, then run 10 users only if p95/p99 are stable and resource usage is acceptable.
4. Replace the resource monitor with reliable process RSS, PostgreSQL connection, lock, wait-event, and slow-query snapshots.
5. Run write/concurrency financial integrity tests only against disposable fixtures or staging-like isolated data.

## Phase 1C Retest Addendum

Phase 1C remediated the Phase 1B read-report blockers and reran the controlled local profiles. See `docs/qa/performance/phase1c-heavy-report-remediation.md`.

Summary:
- 1 user, 3 minutes: 81 requests, 0 failures, aggregate p95 1500 ms, p99 2000 ms.
- 5 users, 5 minutes: 630 requests, 0 failures, aggregate p95 1500 ms, p99 1800 ms.
- 10 users, 10 minutes: 2496 requests, 0 failures, aggregate p95 1600 ms, p99 2400 ms.
- Receivables aging invoice improved from about 8.2s average / 9.5s p95 to 1.8s average / 2.0s p95 at 5 users.
- Receivables open-items improved from about 3.0-3.5s under 5 users to 1.5s average / 1.7s p95.
- Voucher-type payables summary no longer uses the slow legacy path for recognized purchase voucher filters; `PINV` now maps to the purchase invoice doc type and uses the summary aggregate.

Updated Phase 1B retest status: Pass for controlled local read-heavy 1-user, 5-user, and bounded 10-user profiles.

Updated Phase 2 recommendation: Conditional readiness for staging-style controlled load preparation, pending reliable resource telemetry and disposable write-concurrency financial integrity checks.
