# Phase 2B.3C.3 - PostgreSQL Telemetry and Endurance Readiness

Date: 2026-10-10  
Environment: local Docker performance stack  
Dataset: Phase 2B.3B full-small fixture, 3 tenants, 4,500 invoices total  
Verdict: **Pass for further controlled read/report scalability testing**

## Scope

This phase enabled PostgreSQL SQL-fingerprint telemetry and ran a capped 10-user read/report endurance profile for 30 minutes. The run used authenticated tenant-scoped users and the existing read-only Phase 2B.3C.2 workload.

No financial writes, fixture resets, fixture regeneration, or concurrency above 10 users were performed.

## Evidence

Configuration and safety:

- `docker-compose.perf.yml`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_pg_stat_statements_enable_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_safety_audit_pre_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_safety_audit_post_restart_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_auth_refresh_endurance_2026-10-10.json`

SQL and endurance:

- `docs/qa/performance/evidence/phase2b/phase2b3c3_sql_fingerprint_smoke_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_stats_history.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_failures.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_exceptions.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_pg_activity.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_pg_stat_statements_top.sql.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_docker_stats.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_financial_before.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_10u_30m_2026-10-10_financial_after.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_docker_stats_recovery_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c3_pg_activity_recovery_2026-10-10.txt`

## PostgreSQL Telemetry Setup

`pg_stat_statements` was enabled through the Docker PostgreSQL command:

- `shared_preload_libraries=pg_stat_statements`
- `pg_stat_statements.track=all`
- `pg_stat_statements.max=10000`

The PostgreSQL container was restarted in the isolated Docker performance environment. The extension was created only in `finacc_perf_local`.

Verification:

| Check | Result |
| --- | --- |
| `shared_preload_libraries` | `pg_stat_statements` |
| Installed extensions | `pg_stat_statements`, `plpgsql` |
| `pg_stat_statements.track` | `all` |
| Strict safety audit after restart | Pass, 13 verified / 0 blocked |

The web container was restarted after PostgreSQL to clear stale connections. The safety audit still passed.

## SQL Smoke

A bounded authenticated smoke pass generated SQL fingerprints. Early top SQL by total execution time showed:

- RBAC permission-code resolution by total time.
- Audit log inserts from real authenticated requests.
- Purchase invoice list cursors.
- GST summary/tax summary aggregate queries.
- Daybook debit/credit aggregate queries.

No single SQL fingerprint was slow enough in the smoke to block endurance. The full endurance SQL list is in the final `pg_stat_statements` evidence.

## Endurance Profile

Profile: 10 users for 30 minutes  
Request path: `Nginx -> Gunicorn -> Django -> PostgreSQL/Redis`  
Workload: authenticated read/report workload from Phase 2B.3C.2  
Stats reset: `pg_stat_statements_reset()` before run

Aggregate result:

| Requests | Failures | RPS | Avg ms | p50 | p95 | p99 | Max ms | Avg bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8,369 | 0 | 4.65 | 150.2 | 120 | 320 | 610 | 1,649.4 | 61,084 |

Acceptance:

| Gate | Result |
| --- | --- |
| Zero unexpected HTTP failures | Pass |
| Aggregate p95 below 2s | Pass |
| Aggregate p99 below 3s | Pass |
| Heavy-report p95 below 3s | Pass |
| No financial mismatch | Pass |
| No tenant isolation failure | Pass |
| No persistent DB contention | Pass |
| No recovery issue after load | Pass |

## Endpoint Metrics

| Endpoint | Count | Avg ms | p50 | p95 | p99 | Max ms | Failures | Avg bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `auth/login` | 10 | 887.5 | 830 | 1600 | 1600 | 1563.8 | 0 | 4322 |
| `entity/context [startup]` | 10 | 1038.9 | 1100 | 1300 | 1300 | 1337.4 | 0 | 767 |
| `cross-tenant/financial-years [denied]` | 10 | 489.4 | 480 | 670 | 670 | 670.2 | 0 | 47 |
| `reports/gstr3b/summary` | 290 | 326.1 | 280 | 550 | 950 | 1219.9 | 0 | 5015 |
| `purchase/invoices/list` | 312 | 296.5 | 260 | 470 | 680 | 985.2 | 0 | 522403 |
| `reports/gstr1/readiness` | 317 | 281.6 | 250 | 430 | 760 | 1649.4 | 0 | 3754 |
| `reports/financial/daybook` | 790 | 214.3 | 180 | 370 | 650 | 962.1 | 0 | 36588 |
| `reports/receivables/aging-invoice` | 445 | 191.1 | 160 | 330 | 610 | 1571.7 | 0 | 199932 |
| `reports/receivables/open-items` | 640 | 174.6 | 150 | 300 | 610 | 1202.0 | 0 | 149746 |
| `reports/gstr1/summary` | 316 | 145.4 | 120 | 280 | 810 | 1142.4 | 0 | 2718 |
| `reports/receivables/aging-summary` | 398 | 151.1 | 130 | 280 | 650 | 877.2 | 0 | 4557 |
| `reports/payables/vendor-outstanding-voucher` | 315 | 143.5 | 120 | 270 | 430 | 618.9 | 0 | 14537 |
| `reports/payables/vendor-outstanding` | 593 | 142.7 | 120 | 260 | 520 | 949.4 | 0 | 14453 |
| `sales/invoices/list` | 312 | 111.0 | 93 | 220 | 330 | 912.1 | 0 | 56962 |
| `reports/financial/ledger-summary` | 442 | 108.8 | 93 | 200 | 380 | 562.8 | 0 | 5537 |
| `sales/invoices/lookup` | 896 | 107.8 | 92 | 200 | 420 | 690.4 | 0 | 47697 |
| `dashboard/home-meta` | 738 | 90.6 | 74 | 170 | 390 | 829.4 | 0 | 14590 |
| `entity/context` | 361 | 68.0 | 59 | 140 | 210 | 299.3 | 0 | 767 |

## SQL Findings

Top SQL fingerprints by total execution time during the 30-minute endurance run:

| Finding | Calls | Total ms | Mean ms | Max ms | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| RBAC permission code resolution | 22,630 | 15,116 | 0.67 | 28.20 | Highest total due to repeated permission checks across authenticated requests. |
| Audit log inserts | 8,374 | 5,908 | 0.71 | 43.08 | Expected from middleware/audit logging on real requests. |
| Daybook debit/credit aggregate | 790 | 2,528 | 3.20 | 18.24 | Stable; no blocking SQL outliers. |
| Customer subscription lookups | 27,621 | 2,031 | 0.07 | 20.56 | Very high call count; candidate for request-scope caching. |
| Sales tax summary aggregation | 633 | 1,911 | 3.02 | 18.00 | Correlates with GST report paths. |
| Posting entries page query | 790 | 1,725 | 2.18 | 9.42 | Daybook path; stable. |
| Ledger summary aggregate | 442 | 1,716 | 3.88 | 63.32 | Occasional max tail but mean is small. |
| Sales invoice count/tax aggregate | 633 | 1,649 | 2.61 | 91.01 | Correlates with GSTR summaries/readiness. |
| Sales invoice lookup projection | 896 | 1,387 | 1.55 | 25.47 | Healthy. |
| Purchase invoice list query | 312 | 1,049 | 3.36 | 76.52 | Payload size is the larger concern, not SQL time. |

Interpretation:

- The largest total SQL cost is repeated authorization/subscription work, not a single slow report query.
- GSTR-3B and GSTR-1 readiness tail latency correlates more with repeated aggregate/report construction than any one extremely slow SQL fingerprint.
- Receivables aging invoice p95 stayed low at 330 ms; its previous Phase 1 issue remains remediated for this dataset.
- Purchase invoice list still has a large payload around 522 KB per response, but its SQL execution mean stayed low.

## Idle-In-Transaction Investigation

During the run, sampled `idle in transaction` entries appeared briefly. Captured details:

- `application_name`: `finacc-perf-local`
- `client_addr`: Docker web container address
- `state`: `idle in transaction`
- `wait_event_type`: `Client`
- `wait_event`: `ClientRead`
- observed query examples:
  - `SELECT plan_limits...`
  - `SELECT customer_subscriptions...`
  - `BEGIN`
- observed transaction ages were extremely short, approximately sub-millisecond to 6 ms in captured samples.

Final post-run activity showed only the psql observer connection active, with no persistent idle-in-transaction backend.

Assessment: **transient sampling artifact or very short request transaction boundary**, not evidence of a leaked transaction in this run. Keep monitoring in longer staging-style runs.

## Resource Telemetry

Docker stats sampled every 15 seconds:

| Service | Max CPU | First memory | Last memory | Max memory |
| --- | ---: | ---: | ---: | ---: |
| web | 249.03% | 536.3 MiB | 556.4 MiB | 696.9 MiB |
| postgres | 112.73% | 61.91 MiB | 66.48 MiB | 72.07 MiB |
| redis | 6.55% | 10.31 MiB | 10.52 MiB | 11.14 MiB |
| nginx | 4.00% | 10.6 MiB | 10.05 MiB | 11.0 MiB |

Recovery snapshot after load:

- web CPU: 0.03%, memory 556.7 MiB
- PostgreSQL CPU: 2.46%, memory 61.71 MiB
- Redis CPU: 0.81%, memory 10 MiB
- Nginx CPU: 0.00%, memory 9.945 MiB
- Final PostgreSQL activity: only observer query active.

No ungranted locks were captured. Web and Nginx log tails contained no error, timeout, traceback, upstream failure, or exception lines.

## Financial Reconciliation

Financial snapshots before and after endurance were identical.

| Entity | Sales invoices | Purchase invoices | AR open | AP open |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 6 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 7 | 1,000 | 500 | 472,000.00 | 236,000.00 |

## Remaining Risks

P1 - Repeated RBAC/subscription queries are the largest SQL total-time contributors.

- Not currently a failure, but they will scale with request count.
- Recommended next optimization: request-scope permission/subscription caching where safe.

P2 - Login burst remains a tail-latency path.

- Startup login p95 was 1.6s during the 30-minute run.
- This does not block read/report browsing but should be tested separately if login churn becomes part of load profiles.

P2 - Purchase invoice list payload remains large.

- About 522 KB per response for 500 purchase rows.
- SQL is not the bottleneck here; payload size and browser rendering should be tested before larger fixtures.

P2 - Local Docker telemetry is still limited.

- Docker stats are point samples.
- No per-Gunicorn-worker breakdown or host/load-generator CPU trace was captured.
- Local results must not be translated into production capacity.

## Verdict

**Pass** for Phase 2B.3C.3.

Recommendation:

- Proceed to the next controlled read/report scalability stage with `pg_stat_statements` enabled.
- Keep 25-user and medium-fixture gates explicit, not automatic.
- Before larger fixture/concurrency runs, consider reducing repeated RBAC/subscription query work and adding continuous host/load-generator telemetry.
