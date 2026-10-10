# Phase 2B.3C.1B - Authenticated Docker API and Financial Reporting Baseline

Date: 2026-10-10  
Environment: local Docker performance stack  
Request path: `localhost:18080 -> Nginx -> Gunicorn -> Django -> PostgreSQL/Redis`  
Dataset: Phase 2B.3B full-small fixture, 3 tenants, 4,500 invoices total  
Verdict: **Pass for Phase 2B.3C.2 controlled single-user-to-low-concurrency read/report testing**

## Scope

This phase established authenticated single-user API baselines across the three isolated performance tenants. It did not run multi-user Locust load, financial writes, resets, fixture generation, or destructive operations.

The benchmark used the completed Phase 2B.3C.1A users:

| Tenant | User | Entity | FY | Subentity |
| --- | --- | ---: | ---: | ---: |
| Small | `perf-api-small@local.invalid` | 5 | 5 | 5 |
| Medium | `perf-api-medium@local.invalid` | 6 | 6 | 6 |
| Large | `perf-api-large@local.invalid` | 7 | 7 | 7 |

## Evidence

- `docs/qa/performance/evidence/phase2b/phase2b3c1b_safety_audit_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_auth_refresh_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_api_baseline_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_endpoint_metrics_2026-10-10.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_financial_before_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_financial_after_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_docker_stats_before_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_docker_stats_after_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_pg_before_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_pg_after_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c1b_pg_extensions_2026-10-10.txt`

Benchmark harness:

- `perf/baseline/phase2b3c1b_authenticated_api_baseline.py`

## Readiness Gates

| Gate | Result |
| --- | --- |
| Docker services healthy | Pass |
| Strict performance safety audit | Pass |
| Database identity | `finacc_perf_local` on Docker PostgreSQL host `postgres` |
| Auth users refreshed through safety-gated command | Pass |
| Tenant isolation | Pass |
| Financial counts unchanged | Pass |
| Read-only benchmark traffic | Pass, except login/session/audit writes required by real auth |

Authentication and cross-tenant checks:

- Each user logged in through Nginx and received real auth cookies.
- Each user saw only its own entity in `/api/entity/me/entities`.
- Cross-tenant financial-year requests returned `404`.
- No cross-tenant reads or tenant leakage were observed.

## Test Parameters

- Samples per endpoint per tenant: 6 total, made of 1 cold request plus 5 warm requests.
- Tenants: 3.
- Endpoint/tenant combinations: 54.
- Total benchmarked endpoint samples: 324, excluding login and denial probes.
- Request timeout: 60 seconds.
- Date scope: `2026-04-01` to `2026-10-10`.
- As-of date: `2026-10-10`.

Important: p95 and p99 are **indicative only** because this phase intentionally used bounded low-volume samples. They are useful for relative local baselines, not reliability claims.

## Endpoint Metrics

Values below show the worst tenant for each endpoint.

| Endpoint | Max tenant p50 ms | Max tenant p95 ms | Max tenant p99 ms | Max ms | Max avg bytes | Errors | Row range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `purchase/invoices/list` | 282.5 | 576.3 | 628.1 | 641.1 | 522735 | 0 | 500-500 |
| `dashboard/home-meta` | 73.5 | 504.7 | 611.0 | 637.6 | 14591 | 0 | 0-0 |
| `reports/financial/daybook` | 254.8 | 352.8 | 386.4 | 395.4 | 36670 | 0 | 50-50 |
| `reports/gstr3b/summary` | 283.4 | 348.7 | 371.5 | 377.5 | 5015 | 0 | 0-0 |
| `reports/receivables/aging-invoice` | 212.3 | 317.1 | 349.6 | 357.7 | 200185 | 0 | 100-100 |
| `reports/receivables/open-items` | 147.5 | 298.1 | 330.5 | 338.6 | 150006 | 0 | 100-100 |
| `reports/gstr1/readiness` | 236.2 | 297.4 | 307.8 | 310.4 | 3754 | 0 | 0-0 |
| `reports/gstr1/summary` | 156.3 | 209.3 | 214.7 | 216.0 | 2718 | 0 | 0-0 |
| `reports/financial/ledger-summary` | 139.5 | 188.4 | 189.1 | 189.2 | 5540 | 0 | 6-6 |
| `reports/payables/vendor-outstanding-voucher` | 144.6 | 179.5 | 186.1 | 187.7 | 14538 | 0 | 1-1 |
| `sales/invoices/lookup` | 103.0 | 166.3 | 175.7 | 178.0 | 47732 | 0 | 100-100 |
| `purchase/invoices/lookup` | 84.7 | 162.2 | 186.8 | 192.9 | 46662 | 0 | 100-100 |
| `reports/payables/vendor-outstanding` | 151.3 | 158.2 | 161.9 | 162.8 | 14454 | 0 | 1-1 |
| `reports/receivables/aging-summary` | 147.2 | 152.7 | 152.8 | 152.8 | 4557 | 0 | 1-1 |
| `sales/invoices/list` | 94.6 | 139.7 | 150.1 | 152.7 | 56962 | 0 | 100-100 |
| `auth/me` | 59.8 | 99.1 | 103.7 | 104.9 | 4256 | 0 | 0-0 |
| `entity/context` | 57.6 | 61.0 | 61.7 | 61.8 | 768 | 0 | 1-1 |
| `reports/sales/gstin` | 41.5 | 44.8 | 45.1 | 45.2 | 1661 | 0 | 1-1 |

## Financial Validation

Financial snapshots before and after the benchmark were identical.

| Entity | Sales invoices | Purchase invoices | AR open | AP open |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 6 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 7 | 1,000 | 500 | 472,000.00 | 236,000.00 |

The benchmark validated that successful HTTP 200 responses were not hiding empty invoice/report datasets for the core list and open-item report paths. GST and dashboard endpoints were validated for successful response contracts but do not naturally expose row counts in the same shape.

## Resource Telemetry

Docker stats before:

| Service | CPU | Memory |
| --- | ---: | ---: |
| web | 0.03% | 420.4 MiB |
| postgres | 2.55% | 185.0 MiB |
| redis | 2.87% | 10.84 MiB |
| nginx | 0.00% | 9.44 MiB |

Docker stats after:

| Service | CPU | Memory |
| --- | ---: | ---: |
| web | 100.79% | 590.8 MiB |
| postgres | 14.34% | 185.2 MiB |
| redis | 0.94% | 10.21 MiB |
| nginx | 0.00% | 10.55 MiB |

PostgreSQL snapshots:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `numbackends` | 1 | 1 | 0 |
| `xact_commit` | 4,947 | 14,920 | 9,973 |
| `xact_rollback` | 3 | 3 | 0 |
| `blks_read` | 3,372 | 3,479 | 107 |
| `blks_hit` | 6,139,566 | 9,183,850 | 3,044,284 |
| `tup_returned` | 5,400,120 | 9,605,209 | 4,205,089 |
| `tup_fetched` | 3,246,194 | 6,329,021 | 3,082,827 |

Locks after the run were only the observation query's `AccessShareLock` and `virtualxid` lock. No blocked or ungranted locks were observed in the captured snapshots.

Limitations:

- `pg_stat_statements` is not installed in the Docker database, so this run captured PostgreSQL activity counters, connection state, and lock snapshots rather than per-query SQL fingerprint timings.
- Docker `stats --no-stream` is a point-in-time sample, not a continuous telemetry trace.

## Comparison With Phase 1

The Phase 1 and Phase 1B/1C baselines used different data volume, runtime conditions, and in some cases lower-level Gunicorn probes. This Phase 2B.3C.1B pass used the full-small Docker fixture, real auth, Nginx, and three isolated tenants.

Notable comparison:

- Receivables aging invoice previously blocked Phase 1B at about 8.2s average / 9.5s p95 under 5 users. In this single-user Docker baseline, worst-tenant p95 was about 317 ms.
- Receivables open-items previously sat around 3.0-3.5s under 5 users before Phase 1C remediation. In this single-user Docker baseline, worst-tenant p95 was about 298 ms.
- Payables vendor outstanding voucher filter was previously a residual risk. In this Docker baseline, `PINV` voucher-filtered summary returned 200 with worst-tenant p95 about 179 ms.
- Financial daybook remains stable locally, with worst-tenant p95 about 353 ms.
- Purchase invoice list is now the largest single response in this baseline: about 523 KB average response size and worst-tenant p95 about 576 ms.

## Findings

P1 - Purchase invoice list returns the full tenant purchase set in this fixture.

- Evidence: `purchase/invoices/list` returned 500 rows and about 523 KB average payload.
- Risk: acceptable for this bounded dataset, but response size may grow poorly with larger tenants or browser rendering.
- Recommendation: keep lookup/search pagination as the preferred UX path and confirm list endpoint pagination semantics before medium fixture tests.

P2 - Dashboard home-meta showed a cold/warm tail.

- Evidence: p50 about 74 ms but p95 about 505 ms and max about 638 ms.
- Risk: likely cache/preview synchronization path or first-hit work; not a blocker at one user.
- Recommendation: watch under Phase 2B.3C.2 and capture continuous worker CPU.

P2 - PostgreSQL query fingerprint telemetry is not available.

- Evidence: installed extensions list includes only `plpgsql`.
- Risk: future SQL-level bottleneck diagnosis will be weaker without `pg_stat_statements`.
- Recommendation: enable `pg_stat_statements` in the Docker performance stack before larger medium/large baselines.

## Verdict

**Pass / Go for Phase 2B.3C.2** with restrictions:

- Continue with controlled low-concurrency authenticated read/report profiles only.
- Do not begin financial write workloads in this track.
- Monitor purchase invoice list payload size and dashboard cold-tail behavior.
- Enable better PostgreSQL SQL fingerprint telemetry before larger datasets or higher concurrency.
