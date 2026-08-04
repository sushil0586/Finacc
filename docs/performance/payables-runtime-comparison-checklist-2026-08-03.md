# Payables Runtime Comparison Checklist

Last updated: 2026-08-04

Status: active checklist for explaining divergent payables stress results across local runtime stacks

Related documents:
- [finacc-next-hardening-plan-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-next-hardening-plan-2026-08-03.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [local-postgres-stress-prerequisites-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/local-postgres-stress-prerequisites-2026-08-03.md:1)

## Purpose

Use this checklist whenever payables stress results diverge sharply between two local or staging runtime stacks.

This exists because on `2026-08-03`:

- earlier payables `100-user / 45-second` evidence on `127.0.0.1:8010` was tail-heavy
- fresh clean reruns on `127.0.0.1:8011` and `127.0.0.1:8012` were healthy
- the simple `threads` explanation did not hold

So future investigation should first ask:

- is the payables code path actually slow?
- or is one runtime stack carrying stale or unrelated pressure?

## When To Use This

Run this checklist when all of the following are true:

- endpoint behavior differs materially between two runtime stacks
- the same code revision is believed to be running
- the same Locust tag set is being used
- failures are absent or low, but latency shape differs a lot

## Stack Identity Checklist

For each compared runtime, record:

1. bind port
2. process start time
3. worker count
4. thread count
5. timeout value
6. python executable path
7. working directory
8. command line used to launch the server

Suggested commands:

```bash
lsof -iTCP:8010 -sTCP:LISTEN -n -P
ps -o pid,ppid,etime,command -p <pid>
ps eww -p <pid>
```

## Environment Checklist

Record whether these differ between the slow and fast stacks:

1. `PAYABLES_PERF_LOGGING`
2. `PAYABLES_AP_AGING_CACHE_ENABLED`
3. `PAYABLES_META_CACHE_ENABLED`
4. `DB_POOL_ENABLED`
5. `DB_POOL_MIN_SIZE`
6. `DB_POOL_MAX_SIZE`
7. `DB_CONN_MAX_AGE`
8. auth/session-related settings if overridden in env

Important:

- do not assume a matching command line means matching runtime behavior
- long-lived processes may have older cache state, different warm data, or earlier environment inheritance

## Runtime Health Checklist

Before rerunning Locust, check:

1. how long the server has been alive
2. whether other requests or tests recently ran through it
3. whether the process shows unusually high accumulated CPU time
4. whether the port is shared by an older long-running master plus reused workers
5. whether logs show previous exceptions, pauses, or resource pressure

Interpretation rule:

- if one stack is much older than the other, treat server age as a real comparison variable

## Cache State Checklist

For each runtime, note:

1. whether cache is warm or cold before the run
2. whether a previous Locust or manual test already primed payables cache entries
3. whether the cache backend is shared across compared stacks
4. whether cache invalidation events may have recently fired

Questions:

- did the slow server have stale or fragmented cache state?
- did the fast server begin from a clean or more favorable cache condition?

## Workload Consistency Checklist

Confirm these are identical across the compared runs:

1. `LOCUST_HOST`
2. user count
3. spawn rate
4. run duration
5. tag set
6. entity
7. financial year
8. subentity
9. AP aging view
10. report date

If any of these differ, do not treat the results as a clean runtime comparison.

## Evidence To Capture

For every runtime comparison, keep:

- Locust stats CSV
- Locust stats history CSV
- Locust HTML report
- [payables_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/payables_perf.log:1)
- output from:
  - `lsof -iTCP:<port> -sTCP:LISTEN -n -P`
  - `ps -o pid,ppid,etime,command -p <pid>`
  - `ps eww -p <pid>`

If payables perf logging is enabled, also run:

```bash
python3 Scripts/analyze_payables_perf_log.py logs/payables_perf.log
```

## Decision Rules

Use these rules after comparison:

- if fresh clean stacks are consistently fast, do not keep treating payables as the top pure query bottleneck
- if only one old stack is slow, classify that as runtime-drift or environment-pressure evidence
- if fresh clean stacks also become slow, return to payables query and request-overhead tuning
- if results remain inconsistent, repeat with a brand-new port and freshly started gunicorn

## Current Working Conclusion On 2026-08-03

Based on observed local reruns:

- clean `8011` with `--workers 4 --threads 8` was healthy
- clean `8012` with `--workers 4 --threads 2` was also healthy
- older long-running `8010` had the heavy-tail story

So the current best explanation is:

- older runtime state or surrounding environment pressure on `8010`
- not a simple thread-count issue
- not enough evidence yet to blame payables query cost alone

## Comparison Update On 2026-08-04

Two comparable `100-user / 45-second` payables-report probes were executed against the older `8010` stack and the fresher `8011` stack.

Stack identity notes captured before rerun:

- `8010`
  - master elapsed time: about `14h 52m`
  - shape: `--workers 4 --threads 2`
  - did not expose `PAYABLES_PERF_LOGGING=true` in the master environment
- `8011`
  - master elapsed time: about `9h 20m`
  - shape: `--workers 4 --threads 8`
  - exposed `PAYABLES_PERF_LOGGING=true`

Commands executed:

```bash
cd Finacc
LOCUST_HOST=http://127.0.0.1:8010 ./venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r15_8010_old_runtime \
  --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r15_8010_old_runtime.html

LOCUST_HOST=http://127.0.0.1:8011 ./venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r16_8011_logged_runtime \
  --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r16_8011_logged_runtime.html
```

Artifacts:
- [results_phase1_payables_reports_100u_45s_2026_08_04_r15_8010_old_runtime_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r15_8010_old_runtime_stats.csv:1)
- [results_phase1_payables_reports_100u_45s_2026_08_04_r16_8011_logged_runtime_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r16_8011_logged_runtime_stats.csv:1)
- [payables_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/payables_perf.log:1)

Result summary:

- `8010` old runtime
  - total requests: `1620`
  - failures: `0`
  - aggregate median: `230 ms`
  - aggregate avg: `756.02 ms`
  - aggregate p95: `3300 ms`
  - aggregate p99: `5800 ms`
  - max: `6004.72 ms`
  - throughput: about `36.72 req/s`
- `8011` fresher logged runtime
  - total requests: `1957`
  - failures: `0`
  - aggregate median: `120 ms`
  - aggregate avg: `266.86 ms`
  - aggregate p95: `1000 ms`
  - aggregate p99: `2200 ms`
  - max: `2871.65 ms`
  - throughput: about `44.40 req/s`

Endpoint highlights:

- `reports/payables/aging [get]`
  - `8010` median `190 ms`, avg `792.62 ms`, p99 `5800 ms`
  - `8011` median `140 ms`, avg `316.52 ms`, p99 `2400 ms`
- `reports/payables/meta [get]`
  - `8010` median `130 ms`, avg `709.80 ms`, p99 `5800 ms`
  - `8011` median `78 ms`, avg `187.88 ms`, p99 `2000 ms`

`8011` perf-log interpretation:

- `ap_aging.api_get`
  - average duration about `118.54 ms`
  - average query count `1`
- `ap_aging.cache_lookup`
  - average duration about `5.82 ms`
  - cache key present in sampled events
- `payables_meta.api_get`
  - average duration about `49.90 ms`
  - average query count `1`
- `payables_selector.asof_advances`
  - average duration about `34.65 ms`
- `payables_selector.open_item_vendor_aging_bucket_summary`
  - average duration about `20.75 ms`

Updated interpretation:

- the slower `8010` result is still reproducible on the older stack
- the fresher `8011` stack remains materially healthier under the same workload
- the `8011` perf log does not support a broad payables query-collapse story
- the remaining payables risk is best classified as runtime drift, cache/process state, or surrounding environment pressure on the older stack

Recommended next check:

- restart a brand-new `8010`-style stack with payables perf logging enabled
- rerun the same `100-user / 45-second` payables tier on that fresh stack
- if the fresh replacement behaves like `8011`, downgrade `8010` from blocker to stale-runtime evidence

Fresh replacement update on `2026-08-04`:

A brand-new `8010`-shape stack was started on `127.0.0.1:8016` using `--workers 4 --threads 2` with `PAYABLES_PERF_LOGGING=true`, then the same `100-user / 45-second` payables-report tier was rerun.

Command executed:

```bash
cd Finacc
PAYABLES_PERF_LOGGING=true ./venv/bin/gunicorn FA.wsgi:application --bind 127.0.0.1:8016 --workers 4 --threads 2 --timeout 120

LOCUST_HOST=http://127.0.0.1:8016 ./venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged \
  --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged.html
```

Artifacts:
- [results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged_stats.csv:1)
- [results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r17_8016_fresh_threads2_logged.html:1)
- [payables_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/payables_perf.log:1)

Result summary:

- `8016` fresh `4 workers / 2 threads`
  - total requests: `2176`
  - failures: `0`
  - aggregate median: `42 ms`
  - aggregate avg: `64.41 ms`
  - aggregate p95: `190 ms`
  - aggregate p99: `300 ms`
  - max: `815.05 ms`
  - throughput: about `49.38 req/s`

Comparison against earlier stacks:

- `8010` old runtime
  - aggregate median: `230 ms`
  - aggregate avg: `756.02 ms`
  - throughput: about `36.72 req/s`
- `8011` fresher logged runtime
  - aggregate median: `120 ms`
  - aggregate avg: `266.86 ms`
  - throughput: about `44.40 req/s`
- `8016` fresh replacement
  - aggregate median: `42 ms`
  - aggregate avg: `64.41 ms`
  - throughput: about `49.38 req/s`

Perf-log interpretation for `8016`:

- `ap_aging.api_get`
  - average duration about `42.03 ms`
  - max duration `268.02 ms`
  - average query count `1`
- `payables_meta.api_get`
  - average duration about `22.36 ms`
  - max duration `99.39 ms`
  - average query count `1`
- `ap_aging.cache_lookup`
  - average duration about `1.77 ms`
  - cache key present in sampled events
- `payables_selector.asof_advances`
  - average duration about `6.33 ms`
- `payables_selector.open_item_vendor_aging_bucket_summary`
  - average duration about `3.27 ms`

Final interpretation after the fresh replacement test:

- the old `8010` slowdown is not required to reproduce on a fresh same-shape runtime
- the payables code path itself is healthy on a clean `4 workers / 2 threads` stack
- the old `8010` stack should now be classified as stale-runtime or environment-drift evidence
- payables should no longer be treated as the top active module-level optimization blocker
