# Finacc Phase 1D - Final Local Performance and Financial Concurrency Certification

Date: 2026-10-10  
Environment: local development workstation, PostgreSQL database `finacc_db`, Django served through Gunicorn on `127.0.0.1:8021`  
Verdict: **Conditional Pass**

## Scope

Phase 1D used the Phase 1A, 1B, and 1C performance framework and evidence to run final local controlled read-load telemetry and targeted financial concurrency checks.

This report does not certify production capacity. All application, PostgreSQL, and load-generator processes ran on the same local machine, so CPU, memory, IO, and connection behavior are local-only indicators.

## Safety And Isolation

Verified before execution:

| Check | Result |
| --- | --- |
| Database vendor | PostgreSQL |
| Database name | `finacc_db` |
| GST environment | `SANDBOX` |
| Whitebooks GSTR1 live save | `False` |
| Whitebooks GSTR3B live file | `False` |
| Application server | Gunicorn, 3 sync workers, timeout 120s |
| Load profile | Controlled 1, 5, and 10 users only |
| Write-concurrency tests | Django test database using existing isolated fixtures |

No production database, live GST filing, payment provider, or external destructive integration was intentionally used.

## Evidence

Primary evidence files:

| Evidence | Path |
| --- | --- |
| 1-user Locust stats | `docs/qa/performance/evidence/locust_phase1d_mixed_1u_1m_r2_2026-10-10_stats.csv` |
| 1-user resource telemetry | `docs/qa/performance/evidence/phase1d_resources_1u_1m_r2_2026-10-10.csv` |
| 5-user Locust stats | `docs/qa/performance/evidence/locust_phase1d_mixed_5u_2m_2026-10-10_stats.csv` |
| 5-user resource telemetry | `docs/qa/performance/evidence/phase1d_resources_5u_2m_2026-10-10.csv` |
| 10-user Locust stats | `docs/qa/performance/evidence/locust_phase1d_mixed_10u_3m_2026-10-10_stats.csv` |
| 10-user resource telemetry | `docs/qa/performance/evidence/phase1d_resources_10u_3m_2026-10-10.csv` |
| Combined summary | `docs/qa/performance/evidence/phase1d_load_resource_summary_2026-10-10.json` |

Telemetry collector added for reuse:

`perf/baseline/phase1d_resource_monitor.py`

The monitor captures Gunicorn and Locust CPU/RSS plus PostgreSQL connection, active-query, idle-in-transaction, wait, lock, conflict, deadlock, block-read, and temp-file counters.

## Controlled Load Results

| Profile | Requests | Failures | Avg | p50 | p95 | p99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 user / 1 min | 29 | 0 | 335 ms | 130 ms | 1,200 ms | 1,400 ms | 1,449 ms |
| 5 users / 2 min | 272 | 0 | 353 ms | 110 ms | 1,600 ms | 2,000 ms | 2,256 ms |
| 10 users / 3 min | 783 | 0 | 378 ms | 110 ms | 1,600 ms | 2,000 ms | 2,548 ms |

Shorter local durations were used for Phase 1D because Phase 1B and 1C already established the longer controlled-load behavior. This run focused on final telemetry and concurrency certification gates.

## Endpoint Observations

| Endpoint | 1 user avg | 5 users avg | 10 users avg | 10 users p95 | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Payables vendor outstanding summary | 1,108 ms | 1,077 ms | 1,114 ms | 1,300 ms | Pass |
| Receivables aging summary | 1,449 ms | 1,464 ms | 1,551 ms | 2,100 ms | Pass with monitoring |
| Receivables aging invoice | Not sampled | 1,870 ms | 1,886 ms | 2,100 ms | Pass with monitoring |
| Receivables open-items | Not sampled | 1,611 ms | 1,591 ms | 1,700 ms | Pass with monitoring |
| Financial daybook | 473 ms | 326 ms | 285 ms | 430 ms | Pass |

No HTTP failures, Locust exceptions, or persistent timeouts were recorded in the 1-, 5-, or 10-user Phase 1D profiles.

## Resource Telemetry

| Profile | App max RSS | App max CPU per process | Loadgen max RSS | Loadgen max CPU per process | Max PG conns | Max active PG conns | Max idle in txn | Max waiting conns | Max ungranted locks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 user / 1 min | 261.8 MB | 72.3% | 79.3 MB | 11.7% | 2 | 2 | 0 | 1 | 0 |
| 5 users / 2 min | 293.6 MB | 98.4% | 91.3 MB | 11.6% | 4 | 3 | 1 | 3 | 0 |
| 10 users / 3 min | 296.9 MB | 99.7% | 100.2 MB | 8.6% | 6 | 4 | 1 | 3 | 0 |

Findings:

- Application workers reached near-saturation on local CPU at 5 and 10 users. This is the main local bottleneck observed in Phase 1D.
- PostgreSQL did not show ungranted locks during the sampled windows.
- PostgreSQL connections rose with user load but did not show runaway growth in these short profiles.
- One idle-in-transaction connection appeared during 5- and 10-user runs. It did not grow, but should remain on the staging watch list.
- The load generator stayed below 12% CPU per process, so it was not the limiting component.
- Database CPU was not directly available from the local PostgreSQL setup. PostgreSQL contention was inferred from connection, wait, lock, and query-age counters.
- Sampling can miss very short SQL spikes. Phase 2 should pair this monitor with PostgreSQL `pg_stat_statements` and slow-query logging.

## Financial Write-Concurrency Matrix

Executed command:

```bash
venv/bin/python manage.py test \
  payments.tests.MetaCacheSingleFlightTests.test_concurrent_requests_share_single_builder_run \
  inventory_ops.tests.InventoryOpsConcurrencyTests \
  reports.tests_controls_destructive_workflows \
  --keepdb
```

Result:

```text
Ran 9 tests in 13.398s
OK
```

| Scenario | Coverage | Result |
| --- | --- | --- |
| Concurrent inventory transfer post/retry | `test_simultaneous_transfer_post_and_retry_create_one_posting` | Pass |
| Concurrent inventory adjustment post/retry | `test_simultaneous_adjustment_post_and_retry_create_one_posting` | Pass |
| Concurrent inventory unpost | `test_simultaneous_unpost_creates_one_reversal_for_each_document_type` | Pass |
| Concurrent inventory cancel | `test_simultaneous_cancel_is_idempotent_for_each_document_type` | Pass |
| Concurrent inventory update/post race | `test_simultaneous_update_and_post_leave_one_complete_posting` | Pass |
| Concurrent cached payment form metadata build | `test_concurrent_requests_share_single_builder_run` | Pass |
| Year-close posting balance, duplicate prevention, rollback | `test_year_close_posts_balanced_entry_prevents_duplicate_and_rolls_back` | Pass |
| Opening generation balance, duplicate prevention, rollback | `test_opening_generation_posts_balanced_entry_prevents_duplicate_and_rolls_back` | Pass |
| Posting setup disabled target exclusion | `test_posting_setup_excludes_disabled_targets_from_applied_result` | Pass |

Financial assertions covered by executed tests:

- Balanced posting entries for year close and opening generation.
- Duplicate prevention for control postings.
- Rollback behavior after forced failures.
- Inventory posting idempotency under concurrent post/retry.
- Inventory reversal/cancel behavior without duplicate movements.
- Update/post race ending in one complete posting state.

## Regression Suite After Concurrency

Executed command:

```bash
venv/bin/python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_voucher_type_uses_filtered_aggregate \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_matches_legacy_item_math_with_stable_query_count \
  reports.tests_receivables \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  reports.tests_books.BookReportAPITests.test_daybook_query_count_does_not_grow_with_page_size \
  sales.tests.SalesComplianceRecoveryUnitTests.test_list_view_honors_page_size_without_changing_array_contract \
  --keepdb
```

Result:

```text
Ran 21 tests in 5.644s
OK
```

The post-concurrency regression suite passed for payables summary aggregation, receivables reports, financial daybook pagination/query-count behavior, and sales list pagination contract.

## Blocked Or Not Yet Certified

The following Phase 1D scenarios were not fully certified because no safe end-to-end disposable workflow was available in the current harness:

| Scenario | Status | Reason |
| --- | --- | --- |
| Concurrent sales invoice creation/posting through actual API contract | Blocked | No deterministic isolated API write-concurrency harness was available in this phase. |
| Concurrent purchase invoice creation/posting through actual API contract | Blocked | No deterministic isolated API write-concurrency harness was available in this phase. |
| Voucher numbering uniqueness/sequencing for concurrent sales/purchase/payment creation | Partial | Inventory/control posting idempotency passed; full sales/purchase/payment document numbering under concurrent creation was not certified. |
| Concurrent payment allocation and outstanding-balance updates | Blocked | Existing tests cover allocation rules and retry behavior, but not a full concurrent database allocation scenario in Phase 1D. |
| Multi-tenant concurrent writes | Blocked | Tenant-scoped tests exist in the suite, but simultaneous cross-tenant write certification was not executed here. |
| Duplicate submission/idempotency across all financial document types | Partial | Inventory and selected payment/control repeat-action behavior are covered; not all source documents are certified. |

These gaps should be treated as Phase 2 entry blockers for high-concurrency write testing, not as read-load blockers.

## P0/P1 Findings

P0:

- None found in the executed Phase 1D controlled read-load profiles or executed concurrency tests.

P1:

- Application workers reached near 100% CPU per process under 5- and 10-user local profiles. Staging should validate with production worker count, CPU allocation, and PostgreSQL separation.
- Full end-to-end write-concurrency certification is incomplete for sales invoice, purchase invoice, payment allocation, voucher numbering, and cross-tenant simultaneous writes.
- One idle-in-transaction connection appeared during 5- and 10-user runs. It did not grow locally, but should be monitored with longer staging runs.
- Local telemetry lacks direct PostgreSQL CPU and `pg_stat_statements` query fingerprints. Phase 2 should enable both.

P2:

- Phase 1D used shortened local profiles to avoid repeating Phase 1B/1C longer runs. This is acceptable for final local certification but not a capacity proof.
- Resource metrics were sampled at intervals, so sub-second SQL spikes may not appear in the CSV.

## Final Verdict

**Conditional Pass**

Finacc is ready to move beyond local read-load remediation for controlled staging validation. The remediated reporting and list endpoints held stable through 1-, 5-, and 10-user local profiles with zero HTTP failures, no observed ungranted PostgreSQL locks, and passing financial/report regression tests.

The condition is write-concurrency coverage: high-concurrency Phase 2 should not include destructive financial write workloads until disposable staging harnesses exist for sales invoice posting, purchase invoice posting, payment allocation, voucher numbering, and simultaneous cross-tenant writes.

## Phase 2 Entry Recommendation

Recommended next step: **Phase 2 staging readiness with restrictions**.

Allowed:

- Staging read/report load with production-like Gunicorn, PostgreSQL separation, `pg_stat_statements`, slow-query logging, and system telemetry.
- Controlled non-destructive API workflows.
- Continued monitoring of payables, receivables aging/open-items, daybook, purchase/sales lists, and dashboard workflows.

Blocked until additional harnesses are added:

- High-concurrency sales invoice posting.
- High-concurrency purchase invoice posting.
- High-concurrency payment allocation.
- Voucher numbering uniqueness/sequencing certification across financial document families.
- Cross-tenant simultaneous write certification.
