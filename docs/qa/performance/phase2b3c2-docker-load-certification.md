# Phase 2B.3C.2 - Docker Multi-Tenant Read/Report Load Certification

Date: 2026-10-10  
Environment: local Docker performance stack  
Path: `Nginx -> Gunicorn -> Django -> PostgreSQL/Redis`  
Dataset: Phase 2B.3B full-small fixture, 3 tenants, 4,500 invoices total  
Verdict: **Pass for next controlled stage, with telemetry improvements recommended**

## Scope

This phase ran authenticated, read-only, multi-tenant load through the full Docker request path. The workload used the three Phase 2B.3C.1A performance users, each restricted to one fixture tenant.

No financial writes, fixture resets, fixture regeneration, lifecycle actions, or 25-user profiles were run.

## Evidence

Workload:

- `perf/locust/phase2b3c2_read_report_load.py`

Safety and authentication:

- `docs/qa/performance/evidence/phase2b/phase2b3c2_safety_audit_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c2_auth_refresh_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c2_financial_initial_2026-10-10.json`

Load profiles:

- `docs/qa/performance/evidence/phase2b/phase2b3c2_1u_3m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c2_5u_5m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c2_10u_10m_2026-10-10_stats.csv`
- Matching `_stats_history.csv`, `_failures.csv`, `_exceptions.csv`, `.html`, Locust logs, Docker stats logs, PostgreSQL activity logs, web logs, Nginx logs, and financial before/after snapshots are saved with the same prefixes.

Post-run Redis:

- `docs/qa/performance/evidence/phase2b/phase2b3c2_redis_ping_after_2026-10-10.txt`

## Readiness Gates

| Gate | Result |
| --- | --- |
| Docker services healthy | Pass |
| Strict safety audit | Pass, 13 verified / 0 blocked |
| Database identity | `finacc_perf_local` |
| Auth users refreshed | Pass |
| Tenant isolation at startup | Pass |
| Cross-tenant denial at startup | Pass |
| Financial fixture counts before load | Pass |
| Redis post-run health | `PONG` |

## Workload

The Locust workload rotated across the three authorized users and included:

- Authentication and entity context.
- Dashboard home metadata.
- Sales invoice lookup and list.
- Purchase invoice lookup and list.
- Financial daybook and ledger summary.
- Receivables aging summary, aging invoice, and open-items.
- Payables vendor outstanding summary and `PINV` voucher-filtered summary.
- GSTR-1 summary/readiness, GSTR-3B summary, and sales GSTIN report.
- Cross-tenant financial-year denial checks during user startup.

Payload validation checked JSON shape and row presence for list/report endpoints that should contain fixture data. Tenant isolation was verified by startup context and cross-tenant denial checks.

## Aggregate Results

| Profile | Requests | Failures | RPS | Avg ms | p50 | p95 | p99 | Max ms | Avg bytes | Financial |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 user / 3 min | 87 | 0 | 0.49 | 132.5 | 110 | 270 | 480 | 477.4 | 37,868 | unchanged |
| 5 users / 5 min | 707 | 0 | 2.36 | 136.1 | 120 | 280 | 400 | 639.9 | 62,783 | unchanged |
| 10 users / 10 min | 2,638 | 0 | 4.40 | 165.4 | 120 | 350 | 820 | 2,720.8 | 61,647 | unchanged |

Acceptance targets:

| Target | Result |
| --- | --- |
| Zero unexpected HTTP failures | Pass |
| Aggregate p95 < 2s | Pass, worst aggregate p95 350 ms |
| Aggregate p99 < 3s | Pass, worst aggregate p99 820 ms |
| Critical heavy-report p95 < 3s | Pass |
| No financial mismatches | Pass |
| No tenant isolation failures | Pass |
| No sustained DB lock saturation | Pass in sampled telemetry |

## 10-User Endpoint Results

| Endpoint | Count | Avg ms | p50 | p95 | p99 | Max ms | Phase 2B.3C.1B max p95 | Amplification | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `reports/gstr3b/summary` | 102 | 381.5 | 280 | 640 | 2600 | 2720.8 | 348.7 | 1.84x | 0 |
| `reports/gstr1/readiness` | 108 | 304.9 | 260 | 590 | 790 | 955.6 | 297.4 | 1.98x | 0 |
| `purchase/invoices/list` | 108 | 297.4 | 260 | 440 | 650 | 742.4 | 576.3 | 0.76x | 0 |
| `reports/receivables/aging-invoice` | 142 | 218.2 | 170 | 360 | 650 | 2626.7 | 317.1 | 1.14x | 0 |
| `reports/financial/daybook` | 252 | 219.3 | 190 | 350 | 750 | 1106.1 | 352.8 | 0.99x | 0 |
| `reports/receivables/open-items` | 181 | 178.6 | 150 | 310 | 510 | 928.9 | 298.1 | 1.04x | 0 |
| `reports/payables/vendor-outstanding-voucher` | 104 | 152.6 | 120 | 290 | 420 | 1134.5 | 179.5 | 1.62x | 0 |
| `reports/receivables/aging-summary` | 131 | 158.1 | 130 | 270 | 590 | 982.2 | 152.7 | 1.77x | 0 |
| `reports/payables/vendor-outstanding` | 172 | 147.0 | 120 | 220 | 950 | 1513.5 | 158.2 | 1.39x | 0 |
| `sales/invoices/lookup` | 281 | 130.5 | 95 | 220 | 1200 | 2534.4 | 166.3 | 1.32x | 0 |
| `dashboard/home-meta` | 243 | 105.5 | 76 | 210 | 660 | 2675.4 | 504.7 | 0.42x | 0 |
| `reports/financial/ledger-summary` | 140 | 150.3 | 95 | 190 | 2400 | 2384.9 | 188.4 | 1.01x | 0 |
| `reports/gstr1/summary` | 89 | 130.1 | 120 | 190 | 220 | 221.4 | 209.3 | 0.91x | 0 |
| `sales/invoices/list` | 87 | 112.7 | 95 | 190 | 800 | 803.6 | 139.7 | 1.36x | 0 |
| `entity/context` | 86 | 79.5 | 60 | 140 | 940 | 943.4 | 61.0 | 2.29x | 0 |

Startup-only auth/context paths had higher tails at 10 users:

- `auth/login`: p95 1,200 ms, p99 1,200 ms, max 1,163 ms.
- `entity/context [startup]`: p95 670 ms, max 670 ms.
- These did not cause failures and are not part of steady-state report browsing, but login burst behavior should remain on the staging watch list.

## Resource Telemetry

Docker stats were sampled every 15 seconds during each run.

| Profile | Web max CPU | Web last memory | PostgreSQL max CPU | PostgreSQL last memory | Redis max CPU | Nginx max CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 user / 3 min | 178.45% | 559.4 MiB | 7.19% | 184.9 MiB | 2.84% | 0.19% |
| 5 users / 5 min | 102.71% | 566.7 MiB | 57.41% | 185.2 MiB | 2.41% | 1.05% |
| 10 users / 10 min | 252.89% | 576.6 MiB | 49.44% | 189.4 MiB | 3.23% | 1.25% |

PostgreSQL telemetry:

| Profile | Max observed connection state | Ungranted locks |
| --- | --- | ---: |
| 1 user / 3 min | active 2 | 0 |
| 5 users / 5 min | active 2, idle 1, idle in transaction 1 | 0 |
| 10 users / 10 min | active 3, idle 3, idle in transaction 1 | 0 |

Nginx and web log tails showed no error, timeout, traceback, or upstream failure lines in the captured post-run tails.

Limitations:

- Load generator ran on the host Python venv; host/load-generator CPU was not continuously sampled separately.
- Docker stats are point samples, not flamegraphs or per-worker CPU.
- `pg_stat_statements` is still not available in the Docker database, so SQL fingerprint timing was not captured.
- Local Docker results do not establish production capacity.

## Financial Reconciliation

Financial snapshots stayed unchanged after every profile.

| Entity | Sales invoices | Purchase invoices | AR open | AP open |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 6 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 7 | 1,000 | 500 | 472,000.00 | 236,000.00 |

## Findings

P1 - Steady read/report load passed 10 local Docker users with strong headroom.

- Aggregate p95 remained 350 ms and aggregate p99 remained 820 ms at 10 users.
- Critical heavy-report p95 values remained well below the 3-second acceptance target.

P2 - Some report max values show occasional tail spikes.

- Examples: GSTR-3B summary max 2.72s, receivables aging invoice max 2.63s, dashboard max 2.68s.
- These did not affect p95 acceptance and caused no errors.
- Recommendation: watch in Phase 2B.3C.3 with continuous telemetry and SQL fingerprints.

P2 - Login burst tail exists.

- 10-user startup login p95 was about 1.2s.
- Not a read/report blocker, but worth monitoring if later tests include frequent login churn.

P2 - One idle-in-transaction connection appeared in 5- and 10-user snapshots.

- It did not grow and no ungranted locks were observed.
- This has appeared in prior phases too; keep it on the watch list for longer runs.

P2 - Purchase invoice list remains a large payload.

- It still returns 500 rows for the fixture tenant and has the largest response payload.
- It passed this run, but larger fixture profiles should prefer lookup/paginated paths and verify browser rendering separately.

## Verdict

**Pass** for the requested Phase 2B.3C.2 gate.

Recommendation for next stage:

- Proceed to a controlled medium-fixture or extended-duration read/report validation only after enabling better SQL telemetry such as `pg_stat_statements`.
- Keep the 25-user profile gated; do not run it automatically.
- Do not add financial write workloads to this read/report track.
