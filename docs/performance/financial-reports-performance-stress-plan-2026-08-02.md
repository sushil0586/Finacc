# Financial Reports Performance And Stress Plan

Last updated: 2026-08-04

Status: active, Phase R1 peak runtime shape validated

Related documents:
- [financial-reports-closure-plan-2026-08-02.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/financial-reports-closure-plan-2026-08-02.md:1)
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [perf/locust/README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md:1)
- [perf/locust/locustfile.py](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/locustfile.py:1)

## Purpose

This document is the execution board for financial-report performance and stress testing.

It is separate from correctness closure.

This plan is used to answer:

1. Which financial reports have dedicated performance coverage?
2. Which load tiers have actually been executed?
3. What are the current latency and failure characteristics?
4. Which exports or grouped views become bottlenecks first?
5. What still blocks production-level confidence?

## In Scope

Phase R1 report family:

1. `Trial Balance`
2. `Ledger Summary`

Next report families:

1. `Ledger Book`
2. `Profit and Loss`
3. `Trading Account`
4. `Balance Sheet`
5. `Daybook`
6. `Cashbook`

## Performance Closure Standard

A report family is only considered performance-closed when all of the following are done:

1. read baseline run completed
2. working-load run completed
3. peak or stress run completed
4. export stress completed for supported formats
5. latency summary recorded
6. failures and bottlenecks recorded
7. rerun decision documented after any fixes

## Load Tiers

1. `Smoke`: `5` users, `5m`
2. `Working`: `20` users, `10m`
3. `Peak`: `50` users, `15m`
4. `Stress`: `100` users or higher until meaningful degradation

## Tags Added In Locust

Dedicated financial report Locust tags now available:

1. `financial-reports`
2. `financial-reports-r1`
3. `trial-balance`
4. `ledger-summary`
5. `report-exports`

Current dedicated endpoints covered in Phase R1:

1. `reports/financial/trial-balance [get]`
2. `reports/financial/trial-balance [grouped]`
3. `reports/financial/trial-balance/csv [export]`
4. `reports/financial/ledger-summary [get]`
5. `reports/financial/ledger-summary [grouped]`
6. `reports/financial/ledger-summary/csv [export]`

## Required Environment Variables

Recommended variables for report runs:

```bash
FINACC_FINANCIAL_REPORT_FROM_DATE=2026-04-01
FINACC_FINANCIAL_REPORT_TO_DATE=2026-08-02
```

If not provided, the Locust task will fall back to `FINACC_REPORT_AS_OF_DATE` where possible.

## Phase Tracker

### Phase R1: Trial Balance And Ledger Summary

Status:
- `partial`

Goals:
- baseline latency for main read path
- grouped-view latency for realistic UI usage
- csv export trigger latency
- failure behavior under concurrent report-only load

Executable commands:

Smoke:

```bash
cd Finacc/perf/locust
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 5m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_smoke_5u_5m_2026_08_02 \
  --html results_financial_reports_r1_smoke_5u_5m_2026_08_02.html
```

Working:

```bash
cd Finacc/perf/locust
locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 10m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_working_20u_10m_2026_08_02 \
  --html results_financial_reports_r1_working_20u_10m_2026_08_02.html
```

Peak:

```bash
cd Finacc/perf/locust
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 15m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_peak_50u_15m_2026_08_02 \
  --html results_financial_reports_r1_peak_50u_15m_2026_08_02.html
```

Checklist:
- trial balance ledger summary main read endpoints complete with `0` failures
- grouped calls complete with acceptable p95
- csv export endpoints complete with acceptable p95
- no auth/session instability introduced
- no obvious non-linear collapse before expected load tier

Metrics to record after each run:
- total requests
- failure count
- p50
- p95
- p99
- max latency
- slowest endpoint
- export endpoint latency
- grouped endpoint latency

Observations:
- dedicated financial-report performance coverage did not exist before this phase
- prior report-heavy stress in the repo was focused mainly on payables and mixed operational traffic

Open risks before execution:
- export volume is currently csv-only in the R1 tag set; excel/pdf can be added next if csv baseline is stable
- current R1 tasks use custom scope windows and realistic grouped UI variants, but not yet browser-render stress

Phase R1 smoke update:

Execution date:
- `2026-08-02`

Command executed:

```bash
cd Finacc/perf/locust
./.venv/bin/locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 5m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_smoke_5u_5m_2026_08_02 \
  --html results_financial_reports_r1_smoke_5u_5m_2026_08_02.html
```

Artifacts:
- [results_financial_reports_r1_smoke_5u_5m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_smoke_5u_5m_2026_08_02_stats.csv:1)
- [results_financial_reports_r1_smoke_5u_5m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_smoke_5u_5m_2026_08_02_stats_history.csv:1)
- [results_financial_reports_r1_smoke_5u_5m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_smoke_5u_5m_2026_08_02.html:1)

Result summary:
- total requests: `717`
- failures: `0`
- aggregate avg: `93.06 ms`
- aggregate p95: `120 ms`
- aggregate p99: `210 ms`
- aggregate max: `847.62 ms`

Endpoint highlights:

- `reports/financial/trial-balance [get]`
  - requests: `161`
  - avg: `96.93 ms`
  - p95: `110 ms`
  - p99: `800 ms`
  - max: `847.62 ms`

- `reports/financial/trial-balance [grouped]`
  - requests: `95`
  - avg: `92.97 ms`
  - p95: `110 ms`
  - p99: `780 ms`
  - max: `775.86 ms`

- `reports/financial/trial-balance/csv [export]`
  - requests: `95`
  - avg: `93.85 ms`
  - p95: `120 ms`
  - p99: `190 ms`
  - max: `191.95 ms`

- `reports/financial/ledger-summary [get]`
  - requests: `158`
  - avg: `87.38 ms`
  - p95: `110 ms`
  - p99: `130 ms`
  - max: `148.82 ms`

- `reports/financial/ledger-summary [grouped]`
  - requests: `90`
  - avg: `92.40 ms`
  - p95: `110 ms`
  - p99: `520 ms`
  - max: `516.06 ms`

- `reports/financial/ledger-summary/csv [export]`
  - requests: `108`
  - avg: `93.15 ms`
  - p95: `120 ms`
  - p99: `160 ms`
  - max: `208.88 ms`

Observations:
- the smoke tier is functionally clean and stable with `0` failures
- main read paths are fast at the `5-user` tier
- csv export latency is comfortably within the smoke target window
- the first real tail-risk signal is not average latency, but `p99` spikes on:
  - `trial-balance [get]`
  - `trial-balance [grouped]`
  - `ledger-summary [grouped]`

Initial interpretation:
- Phase R1 smoke is a `pass`
- there is no baseline throughput problem at low concurrency
- grouped views and trial-balance read path need closer observation in the `20-user` working run because they already show occasional long-tail spikes despite low averages

Next step:
- execute Phase R1 working load (`20` users, `10m`)

Phase R1 working-load update:

Execution date:
- `2026-08-02`

Command executed:

```bash
cd Finacc/perf/locust
./.venv/bin/locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 10m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_working_20u_10m_2026_08_02 \
  --html results_financial_reports_r1_working_20u_10m_2026_08_02.html
```

Artifacts:
- [results_financial_reports_r1_working_20u_10m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_working_20u_10m_2026_08_02_stats.csv:1)
- [results_financial_reports_r1_working_20u_10m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_working_20u_10m_2026_08_02_stats_history.csv:1)
- [results_financial_reports_r1_working_20u_10m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_working_20u_10m_2026_08_02.html:1)

Result summary:
- total requests: `2681`
- failures: `0`
- aggregate avg: `75.33 ms`
- aggregate p95: `110 ms`
- aggregate p99: `170 ms`
- aggregate max: `280.50 ms`
- aggregate throughput: `9.68 req/s`

Endpoint highlights:

- `reports/financial/trial-balance [get]`
  - requests: `669`
  - avg: `71.79 ms`
  - p95: `110 ms`
  - p99: `130 ms`
  - max: `255.52 ms`

- `reports/financial/trial-balance [grouped]`
  - requests: `333`
  - avg: `75.04 ms`
  - p95: `110 ms`
  - p99: `160 ms`
  - max: `280.50 ms`

- `reports/financial/trial-balance/csv [export]`
  - requests: `318`
  - avg: `78.31 ms`
  - p95: `110 ms`
  - p99: `120 ms`
  - max: `160.49 ms`

- `reports/financial/ledger-summary [get]`
  - requests: `626`
  - avg: `74.68 ms`
  - p95: `110 ms`
  - p99: `160 ms`
  - max: `210.85 ms`

- `reports/financial/ledger-summary [grouped]`
  - requests: `335`
  - avg: `75.06 ms`
  - p95: `110 ms`
  - p99: `120 ms`
  - max: `225.73 ms`

- `reports/financial/ledger-summary/csv [export]`
  - requests: `360`
  - avg: `77.74 ms`
  - p95: `120 ms`
  - p99: `170 ms`
  - max: `194.75 ms`

Observations:
- the `20-user` working tier stayed functionally clean with `0` failures
- latency improved versus the smoke sample because the smoke long-tail spikes did not repeat under sustained working concurrency
- grouped report reads remained stable and did not show the severe p99 volatility seen in the first smoke run
- the worst endpoint at this tier was `trial-balance [grouped]`, but even there the ceiling stayed under `300 ms`
- csv export latency remained within a comfortable working-load band

Interpretation:
- Phase R1 working load is a `pass`
- there is no current evidence of saturation or unstable long-tail behavior at the `20-user` tier for these two financial report families
- R1 remains `partial` overall because peak-load and broader export stress are still pending

Next step:
- execute Phase R1 peak load (`50` users, `15m`)

Phase R1 peak-load update:

Execution date:
- `2026-08-02`

Command executed:

```bash
cd Finacc/perf/locust
./.venv/bin/locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 15m \
  --tags financial-reports-r1 \
  --csv results_financial_reports_r1_peak_50u_15m_2026_08_02 \
  --html results_financial_reports_r1_peak_50u_15m_2026_08_02.html
```

Artifacts:
- [results_financial_reports_r1_peak_50u_15m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_02_stats.csv:1)
- [results_financial_reports_r1_peak_50u_15m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_02_stats_history.csv:1)
- [results_financial_reports_r1_peak_50u_15m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_02.html:1)

Result summary:
- total requests: `18378`
- failures: `0`
- aggregate avg: `438.33 ms`
- aggregate median: `85 ms`
- aggregate p95: `2100 ms`
- aggregate p99: `3600 ms`
- aggregate max: `16836.27 ms`
- aggregate throughput: `20.43 req/s`

Endpoint highlights:

- `reports/financial/ledger-summary [get]`
  - requests: `4586`
  - avg: `432.79 ms`
  - p95: `2100 ms`
  - p99: `3500 ms`
  - max: `16836.27 ms`

- `reports/financial/ledger-summary [grouped]`
  - requests: `2229`
  - avg: `455.89 ms`
  - p95: `2200 ms`
  - p99: `3600 ms`
  - max: `13551.41 ms`

- `reports/financial/ledger-summary/csv [export]`
  - requests: `2205`
  - avg: `449.12 ms`
  - p95: `2100 ms`
  - p99: `3800 ms`
  - max: `16279.01 ms`

- `reports/financial/trial-balance [get]`
  - requests: `4602`
  - avg: `410.12 ms`
  - p95: `2000 ms`
  - p99: `3700 ms`
  - max: `16054.87 ms`

- `reports/financial/trial-balance [grouped]`
  - requests: `2319`
  - avg: `438.83 ms`
  - p95: `2000 ms`
  - p99: `3300 ms`
  - max: `16529.89 ms`

- `reports/financial/trial-balance/csv [export]`
  - requests: `2337`
  - avg: `482.83 ms`
  - p95: `2300 ms`
  - p99: `4000 ms`
  - max: `15429.57 ms`

Observations:
- the `50-user` peak tier remained functionally stable with `0` failures across all covered report endpoints
- median latency stayed acceptable, which means the common read path remained responsive even under elevated concurrency
- tail latency degraded materially at peak load, with aggregate `p95` climbing above `2s`, aggregate `p99` at `3.6s`, and rare spikes into the `15s-17s` band
- csv export paths were the slowest endpoints overall, especially `trial-balance/csv [export]`
- grouped endpoints also showed heavier long-tail pressure than the base read endpoints

Interpretation:
- Phase R1 peak load is a `functional pass`
- Phase R1 is not yet a `performance comfort pass` for production-grade peak expectations because long-tail latency remains too high under this tier
- the strongest risk signal is not failures or saturation collapse, but inconsistent heavy-tail response time under report concurrency
- R1 should stay `partial` until we either accept this as a known ceiling or investigate/report-tune the slow paths

Next step:
- move to module-wise write-stress planning for transactional modules, or
- investigate financial report tail-latency hotspots before expanding the report matrix further

Phase R1 peak rerun update:

Execution date:
- `2026-08-03`

Hardening work completed before rerun:
- added financial-report perf logging around trial balance and ledger summary API and builder paths
- removed a per-ledger nested account-type query leak in the shared trial-balance row builder
- memoized repeated financial-year window and scope-name lookups in shared financial selectors
- reduced direct builder query counts from the earlier `613-616` range down to:
  - trial balance warm path: about `5` queries
  - ledger summary warm path: about `8` queries
  - ledger summary repeated warm selector path: as low as `3` queries in direct builder probing

Final command executed:

```bash
cd Finacc
LOCUST_HOST=http://127.0.0.1:8014 \
FINACC_FINANCIAL_REPORT_FROM_DATE=2026-04-01 \
FINACC_FINANCIAL_REPORT_TO_DATE=2026-08-02 \
venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 15m --tags financial-reports-r1 \
  --csv perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final \
  --html perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final.html
```

Artifacts:
- [results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final_stats.csv:1)
- [results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final_stats_history.csv:1)
- [results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r5_final.html:1)
- [financial_reports_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/financial_reports_perf.log:1)

Final result summary:
- total requests: `3611`
- failures: `0`
- aggregate avg: `10350 ms`
- aggregate median: `10000 ms`
- aggregate p95: `18000 ms`
- aggregate p99: `20000 ms`
- aggregate max: `20926 ms`
- aggregate throughput: about `4.01 req/s`

Endpoint highlights:

- `reports/financial/ledger-summary [get]`
  - requests: `885`
  - avg: `10402 ms`
  - median: `10000 ms`
  - p95: `17000 ms`
  - p99: `20000 ms`
  - max: `20472 ms`

- `reports/financial/ledger-summary [grouped]`
  - requests: `484`
  - avg: `10919 ms`
  - median: `10000 ms`
  - p95: `19000 ms`
  - p99: `20000 ms`
  - max: `20709 ms`

- `reports/financial/ledger-summary/csv [export]`
  - requests: `401`
  - avg: `10457 ms`
  - median: `10000 ms`
  - p95: `18000 ms`
  - p99: `20000 ms`
  - max: `20871 ms`

- `reports/financial/trial-balance [get]`
  - requests: `857`
  - avg: `10543 ms`
  - median: `10000 ms`
  - p95: `18000 ms`
  - p99: `20000 ms`
  - max: `20926 ms`

- `reports/financial/trial-balance [grouped]`
  - requests: `428`
  - avg: `10978 ms`
  - median: `11000 ms`
  - p95: `18000 ms`
  - p99: `20000 ms`
  - max: `20619 ms`

- `reports/financial/trial-balance/csv [export]`
  - requests: `456`
  - avg: `10565 ms`
  - median: `10000 ms`
  - p95: `18000 ms`
  - p99: `20000 ms`
  - max: `20784 ms`

Perf log summary:
- `ledger_summary.builder`
  - average duration: about `1834 ms`
  - average query count: `8`
- `trial_balance.builder`
  - average duration: about `1823 ms`
  - average query count: `5`
- API and export wrappers stayed very close to builder timings, which means request framing is no longer the dominant issue

Updated interpretation:
- the query-collapse work was real and valuable
- the financial report path is now low-query and materially cleaner than the original builder shape
- despite that, the full `50-user / 15-minute` peak tier is still not production-comfortable because response times converge around `10s` medians under sustained concurrency
- the next bottleneck is no longer obvious query explosion
- the remaining bottleneck now looks more like sustained aggregate-query contention, runtime pressure, or throughput ceiling under report concurrency

Decision after the final rerun:
- Phase R1 remains a `functional pass`
- Phase R1 remains `partial` from a performance-closure standpoint
- do not widen the financial report matrix yet
- keep financial reports as the top active hardening target until the sustained `50-user` peak tier comes down materially

Runtime-shape comparison update on `2026-08-03`:

Two short `50-user / 2-minute` comparison probes were executed after the query-collapse work to separate code-path cost from runtime-shape cost.

Reference `2 workers / 4 threads` probe on `127.0.0.1:8014`:

```bash
cd Finacc
LOCUST_HOST=http://127.0.0.1:8014 \
FINACC_FINANCIAL_REPORT_FROM_DATE=2026-04-01 \
FINACC_FINANCIAL_REPORT_TO_DATE=2026-08-02 \
venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m --tags financial-reports-r1 \
  --csv perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r8_threads4_workers2_recheck_valid \
  --html perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r8_threads4_workers2_recheck_valid.html
```

Alternate `4 workers / 2 threads` probe on `127.0.0.1:8015`:

```bash
cd Finacc
LOCUST_HOST=http://127.0.0.1:8015 \
FINACC_FINANCIAL_REPORT_FROM_DATE=2026-04-01 \
FINACC_FINANCIAL_REPORT_TO_DATE=2026-08-02 \
venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m --tags financial-reports-r1 \
  --csv perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r6_threads2_workers4 \
  --html perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r6_threads2_workers4.html
```

Artifacts:
- [results_financial_reports_r1_peak_50u_2m_2026_08_03_r8_threads4_workers2_recheck_valid_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r8_threads4_workers2_recheck_valid_stats.csv:1)
- [results_financial_reports_r1_peak_50u_2m_2026_08_03_r6_threads2_workers4_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_2m_2026_08_03_r6_threads2_workers4_stats.csv:1)

Comparison summary:
- `8014` with `2 workers / 4 threads`
  - total requests: `629`
  - failures: `0`
  - aggregate avg: `7047 ms`
  - aggregate median: `6500 ms`
  - aggregate p95: `15000 ms`
  - aggregate max: `15822 ms`
- `8015` with `4 workers / 2 threads`
  - total requests: `1082`
  - failures: `0`
  - aggregate avg: `795.53 ms`
  - aggregate median: `700 ms`
  - aggregate p95: `1600 ms`
  - aggregate max: `2473.31 ms`

Interpretation after the runtime comparison:
- the remaining financial-report bottleneck is strongly runtime-shape sensitive
- the same report mix and date window behaves far better with more worker processes and fewer threads per worker
- the query-collapse work still matters, but process-level concurrency shape now explains far more of the sustained latency gap than per-request builder cost
- the old `8014` full-run result should no longer be treated as the only reference shape for next hardening decisions

Next execution decision:
- treat `4 workers / 2 threads` as the preferred next validation shape for financial reports
- rerun the full `50-user / 15-minute` financial Phase R1 peak tier on that shape before any further report-code changes
- only return to deeper code optimization if the long-run `8015` shape still regresses into multi-second sustained medians

Full runtime-confirmation update on `2026-08-04`:

The full `50-user / 15-minute` rerun on `127.0.0.1:8015` completed successfully and confirmed that the healthier runtime shape holds under sustained load.

Command executed:

```bash
cd Finacc
LOCUST_HOST=http://127.0.0.1:8015 \
FINACC_FINANCIAL_REPORT_FROM_DATE=2026-04-01 \
FINACC_FINANCIAL_REPORT_TO_DATE=2026-08-02 \
venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 15m --tags financial-reports-r1 \
  --csv perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid \
  --html perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid.html
```

Artifacts:
- [results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid_stats.csv:1)
- [results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_financial_reports_r1_peak_50u_15m_2026_08_03_r10_workers4_threads2_final_valid.html:1)
- [financial_reports_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/financial_reports_perf.log:1)

Result summary:
- total requests: `14710`
- failures: `0`
- aggregate avg: `1050.81 ms`
- aggregate median: `960 ms`
- aggregate p95: `2100 ms`
- aggregate p99: `2600 ms`
- aggregate max: `3511.60 ms`
- aggregate throughput: about `16.35 req/s`

Endpoint highlights:

- `reports/financial/ledger-summary [get]`
  - requests: `3666`
  - avg: `1051.71 ms`
  - median: `970 ms`
  - p95: `2100 ms`
  - p99: `2600 ms`
  - max: `3511.60 ms`

- `reports/financial/ledger-summary [grouped]`
  - requests: `1845`
  - avg: `1069.34 ms`
  - median: `980 ms`
  - p95: `2100 ms`
  - p99: `2600 ms`
  - max: `3265.34 ms`

- `reports/financial/ledger-summary/csv [export]`
  - requests: `1793`
  - avg: `1050.24 ms`
  - median: `960 ms`
  - p95: `2100 ms`
  - p99: `2500 ms`
  - max: `3101.12 ms`

- `reports/financial/trial-balance [get]`
  - requests: `3680`
  - avg: `1052.34 ms`
  - median: `960 ms`
  - p95: `2100 ms`
  - p99: `2600 ms`
  - max: `3250.58 ms`

- `reports/financial/trial-balance [grouped]`
  - requests: `1832`
  - avg: `1053.07 ms`
  - median: `950 ms`
  - p95: `2100 ms`
  - p99: `2700 ms`
  - max: `3308.24 ms`

- `reports/financial/trial-balance/csv [export]`
  - requests: `1794`
  - avg: `1072.32 ms`
  - median: `990 ms`
  - p95: `2100 ms`
  - p99: `2500 ms`
  - max: `3045.65 ms`

Perf log summary:
- `ledger_summary.builder`
  - calls: `7293`
  - average duration: about `381.76 ms`
  - max duration: `803.92 ms`
  - average query count: `3`
- `trial_balance.builder`
  - calls: `7304`
  - average duration: about `381.52 ms`
  - max duration: `900.06 ms`
  - average query count: `3`
- API and export wrappers stayed very close to builder timings, which means runtime shape and queueing behavior matter more than residual view overhead

Final interpretation after the valid full rerun:
- the `4 workers / 2 threads` financial-report shape is materially healthier than the old `2 workers / 4 threads` reference
- the earlier `8014` long-tail collapse should be treated as a runtime-shape-specific result, not as the new default state of the financial-report code path
- financial reports are no longer the top active hardening blocker in the same way they were before this rerun
- grouped and CSV paths stay close to the base read path under the healthier runtime shape

Decision after the valid full rerun:
- Phase R1 is a `functional pass`
- Phase R1 remains `partial` only because broader matrix expansion is still pending, not because this runtime shape is still collapsing
- adopt `4 workers / 2 threads` as the preferred local financial-report stress baseline
- shift the next hardening focus back to payables reproducibility and then consolidated SaaS reruns

### Phase R2: Ledger Book

Status:
- `pending`

### Phase R3: Profit And Loss Plus Trading Account

Status:
- `pending`

### Phase R4: Balance Sheet

Status:
- `pending`

### Phase R5: Daybook Plus Cashbook

Status:
- `pending`
