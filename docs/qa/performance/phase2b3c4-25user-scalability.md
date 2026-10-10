# Finacc Phase 2B.3C.4 - Controlled 25-User Docker Read/Report Scalability Certification

Date: 2026-10-10  
Environment: local Docker performance stack  
Database: `finacc_perf_local` on Docker PostgreSQL service  
Path under test: Nginx -> Gunicorn -> Django -> PostgreSQL/Redis  
Dataset: 3 isolated performance tenants, 1,000 sales invoices and 500 purchase invoices per tenant; 4,500 invoices total.

## Verdict

**Pass for the controlled local Docker 25-user read/report scalability gate.**

The gated 10-user, 15-user, and 25-user profiles completed with:

- Zero Locust-recorded HTTP failures.
- Zero Locust exceptions.
- Zero financial snapshot drift.
- Cross-tenant denial checks remained successful.
- Aggregate p95 stayed below 2 seconds.
- Aggregate p99 stayed below 3 seconds.
- No sampled deadlocks, connection exhaustion, or sustained post-test resource saturation.

This is not a production-capacity claim. It certifies only this local Docker dataset, hardware, worker configuration, and read/report workload.

## Safety And Readiness

Safety gate evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c4_safety_audit_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_db_identity_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_auth_refresh_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_financial_initial_2026-10-10.json`

The run used the same authenticated read/report Locust workload from Phase 2B.3C.2/2B.3C.3:

- `perf/locust/phase2b3c2_read_report_load.py`
- Read/report endpoints only.
- Same tenant rotation, think times, endpoint parameters, and validation checks.
- No fixture reset, regeneration, or financial write/lifecycle load.
- `pg_stat_statements` reset before each profile for profile-local SQL fingerprints.

## Profile Summary

| Profile | Duration | Requests | Failures | RPS | Avg | p50 | p95 | p99 | Max | Financial Snapshot |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 10 users | 5 min | 1,411 | 0 | 4.73 | 172 ms | 130 ms | 420 ms | 830 ms | 1,388 ms | Unchanged |
| 15 users | 5 min | 2,096 | 0 | 7.00 | 188 ms | 130 ms | 530 ms | 980 ms | 1,637 ms | Unchanged |
| 25 users | 10 min | 6,787 | 0 | 11.33 | 230 ms | 140 ms | 720 ms | 1,800 ms | 3,094 ms | Unchanged |

Comparison to Phase 2B.3C.3 10-user endurance:

| Run | Duration | Requests | RPS | Avg | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phase 2B.3C.3 10 users | 30 min | 8,369 | 4.65 | 150 ms | 320 ms | 610 ms | 1,649 ms |
| Phase 2B.3C.4 10 users | 5 min | 1,411 | 4.73 | 172 ms | 420 ms | 830 ms | 1,388 ms |
| Phase 2B.3C.4 25 users | 10 min | 6,787 | 11.33 | 230 ms | 720 ms | 1,800 ms | 3,094 ms |

The 25-user run showed expected tail-latency amplification but stayed within the aggregate p95/p99 gates.

## 25-User Endpoint Tail Latency

| Endpoint | Requests | p95 | p99 | Max | Avg Payload |
|---|---:|---:|---:|---:|---:|
| `auth/login` | 25 | 2,400 ms | 2,600 ms | 2,599 ms | 4.2 KB |
| `entity/context [startup]` | 25 | 2,100 ms | 2,100 ms | 2,099 ms | 0.7 KB |
| `reports/receivables/aging-invoice` | 355 | 1,100 ms | 1,900 ms | 2,943 ms | 195.3 KB |
| `reports/gstr3b/summary` | 252 | 980 ms | 2,000 ms | 2,671 ms | 4.9 KB |
| `reports/gstr1/readiness` | 225 | 910 ms | 1,700 ms | 2,586 ms | 3.7 KB |
| `purchase/invoices/list` | 258 | 900 ms | 1,400 ms | 2,043 ms | 510.2 KB |
| `reports/payables/vendor-outstanding` | 511 | 800 ms | 2,000 ms | 2,816 ms | 14.1 KB |
| `reports/receivables/open-items` | 483 | 760 ms | 2,400 ms | 2,849 ms | 146.3 KB |
| `reports/financial/daybook` | 604 | 710 ms | 1,600 ms | 3,094 ms | 35.8 KB |
| `sales/invoices/list` | 258 | 530 ms | 1,800 ms | 2,873 ms | 55.6 KB |

Heavy financial reports stayed below the agreed 3-second p95 budget. A few single max samples crossed 3 seconds, with daybook max at 3,094 ms, but aggregate p99 remained below the gate.

## Resource Telemetry

| Profile | Web Max CPU | Web Memory First -> Last / Max | PostgreSQL Max CPU | PostgreSQL Memory First -> Last / Max | Max Sampled DB Backends |
|---|---:|---|---:|---|---:|
| 10 users | 280% | 556.6 -> 558.7 MiB / 696.5 MiB | 59.8% | 69.6 -> 62.7 MiB / 71.1 MiB | 4 |
| 15 users | 200% | 559.0 -> 560.5 MiB / 672.6 MiB | 72.6% | 68.6 -> 63.8 MiB / 77.0 MiB | 4 |
| 25 users | 333% | 628.2 -> 557.9 MiB / 703.5 MiB | 141.7% | 69.4 -> 71.6 MiB / 81.6 MiB | 4 |

Recovery snapshot after the 25-user profile:

- Web: 0.02% CPU, 557.6 MiB RSS.
- PostgreSQL: 0.00% CPU, 67.77 MiB RSS.
- Redis: 2.73% CPU, 10.2 MiB RSS.
- Nginx: 0.00% CPU, 10.32 MiB RSS.
- PostgreSQL recovery sample: one active observer connection, zero deadlocks.

No sustained memory growth was observed across the gated profiles. CPU bursts were visible in the web and PostgreSQL containers during ramp-up and heavy-report overlap.

## SQL Findings

Top `pg_stat_statements` fingerprints from the 25-user profile:

| SQL Area | Calls | Total SQL Time | Mean | Max | Notes |
|---|---:|---:|---:|---:|---|
| RBAC permission resolution | 18,416 | 12,361 ms | 0.67 ms | 90 ms | Largest cumulative SQL cost; repeated permission-code reads per request. |
| Audit log inserts | 6,800 | 4,675 ms | 0.69 ms | 147 ms | Expected per-request write overhead even for read endpoints. |
| Daybook debit/credit aggregate | 605 | 2,025 ms | 3.35 ms | 16 ms | Query itself is stable; endpoint tail likely includes Python/serialization and concurrency queueing. |
| Subscription lookup | 22,375 | 1,677 ms | 0.07 ms | 34 ms | Low mean but high call volume. |
| Ledger summary aggregate | 407 | 1,562 ms | 3.84 ms | 43 ms | Stable SQL. |
| GSTR sales tax summary | 444 | 1,433 ms | 3.23 ms | 25 ms | Stable SQL. |
| Purchase invoice list query | 253 | 1,022 ms | 4.04 ms | 14 ms | SQL is not the primary issue; response payload remains large. |
| Payables summary optimized SQL | 513 | 595 ms | 1.16 ms | 16 ms | Healthy under this workload. |

The main scalability risks are cumulative per-request auth/RBAC/subscription work, audit logging overhead, and response serialization/payload transfer for the large list/report endpoints.

## Purchase Invoice Payload

The purchase invoice list remained the largest payload in the workload:

- 10 users: ~522 KB average payload.
- 15 users: ~522 KB average payload.
- 25 users: ~522 KB average payload.

Its SQL mean was low in `pg_stat_statements`, so the remaining cost is likely serialization, transfer, and client-side payload handling rather than database execution.

## Tenant And Financial Integrity

Before/after financial snapshots matched for every gated profile:

- 10 users: unchanged.
- 15 users: unchanged.
- 25 users: unchanged.
- Final snapshot after recovery: unchanged from the initial Phase 2B.3C.4 snapshot.

Cross-tenant denial checks were executed during user startup in every profile and recorded zero Locust failures. No tenant isolation violation was observed.

## Observations

- The 25-user aggregate p95 and p99 passed the stated gates.
- Startup/login endpoints showed the highest p95 during ramp-up. This is expected because all users authenticate in a burst at profile start.
- Heavy read/report endpoints showed higher p99/max under 25 users but stayed within p95 budgets.
- Nginx tail logs include a small number of `499` client-closed entries around Locust shutdown boundaries; Locust recorded zero failures and zero exceptions.
- PostgreSQL sampled `idle in transaction` briefly during 15-user and 25-user profiles, but recovery showed no persistent idle transaction. Continue monitoring this in longer runs.
- `pg_stat_database.temp_bytes` is cumulative since database statistics startup and should not be interpreted as profile-local temp usage.

## Evidence

Core summary:

- `docs/qa/performance/evidence/phase2b/phase2b3c4_summary_2026-10-10.json`

10-user evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_stats_history.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_pg_stat_statements_top.sql.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_docker_stats.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_pg_activity.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_financial_before.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_10u_5m_2026-10-10_financial_after.json`

15-user evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_stats_history.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_pg_stat_statements_top.sql.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_docker_stats.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_pg_activity.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_financial_before.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_15u_5m_2026-10-10_financial_after.json`

25-user evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_stats.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_stats_history.csv`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_pg_stat_statements_top.sql.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_docker_stats.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_pg_activity.log`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_financial_before.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_25u_10m_2026-10-10_financial_after.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_docker_stats_recovery_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3c4_pg_activity_recovery_2026-10-10.txt`

## Recommendations

Before pushing beyond 25 local Docker users or moving to a medium/large fixture:

1. Cache request-scope RBAC permission resolution and subscription/plan lookups where safe.
2. Consider asynchronous or batched audit logging for high-volume read/report endpoints, preserving audit requirements.
3. Reduce purchase invoice list payload size through explicit field projection or consumer-driven pagination/page-size limits without silently removing required fields.
4. Continue monitoring brief idle-in-transaction samples in longer-duration runs.
5. Run the next scalability gate in a production-like environment before making capacity claims.

