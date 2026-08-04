# Finacc SaaS Phase A 100-User Baseline Execution

Last updated: 2026-08-04

Status: Phase A.0 read-modern passed cleanly; Phase A.1 purchase mixed now has a clean zero-failure replacement on validated runtime; Phase A.3 broad-read fresh-stack validation is healthy again

Related documents:
- [finacc-saas-1000-user-readiness-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-saas-1000-user-readiness-plan-2026-08-01.md:1)
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [finacc-next-hardening-plan-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-next-hardening-plan-2026-08-03.md:1)
- [perf/locust/README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md:1)

## Current Gating Note

As of `Tuesday, August 4, 2026`, the earlier hardening gate has been reduced materially:

- financial reports now have a validated healthy `4 workers / 2 threads` runtime shape
- payables now have healthy fresh-stack evidence and the older `8010` slowdown is classified as stale-runtime drift

This means:

- formal Phase A consolidation is active again
- the read-modern family has now been executed as the first official Phase A rung
- purchase mixed has now been re-executed cleanly at the same `50-user / 20-minute` tier
- broad-read is no longer blocked by the earlier stale-runtime degradation snapshot
- the next practical rung is legacy comparison, with the official broad-read replacement now complete

## Fresh-Stack Correction

As of `Tuesday, August 4, 2026`, the earlier Phase A.3 broad-read concern needs an explicit correction.

The first `50-user / 20-minute` broad-read run on `127.0.0.1:8015` showed helper failures and severe latency, but a fresh instrumented rerun on `127.0.0.1:8017` no longer reproduces that collapse.

This strongly suggests the earlier broad-read degradation was dominated by stale-runtime drift rather than a persistent code-path regression in sales list or lookup handling.

Fresh validation evidence:

- runtime: `127.0.0.1:8017`
- Gunicorn shape: `4 workers / 2 threads`
- flags: `SALES_PERF_LOGGING=true`, `PAYABLES_PERF_LOGGING=true`, `FINANCIAL_REPORTS_PERF_LOGGING=true`
- workload: `50 users / 5 minutes / --tags read`
- artifact: [results_saas_phaseA_read_50u_5m_2026_08_04_r3_8017_sales_perf_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_50u_5m_2026_08_04_r3_8017_sales_perf_stats.csv:1)
- HTML: [results_saas_phaseA_read_50u_5m_2026_08_04_r3_8017_sales_perf.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_50u_5m_2026_08_04_r3_8017_sales_perf.html)
- sales perf log: [sales_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/sales_perf.log:1)

Observed aggregate outcome:

- requests: `7,357`
- failures: `0`
- average latency: `65 ms`
- median latency: `56 ms`
- p95 latency: `130 ms`
- p99 latency: `220 ms`
- max latency: `620 ms`
- throughput: `24.54 req/s`

Sales endpoint evidence from the same run:

- `sales/invoices [list]`: `613` requests, average `70 ms`, median `63 ms`, p95 `110 ms`, p99 `170 ms`
- `sales/invoices/lookup [list]`: `495` requests, average `76 ms`, median `70 ms`, p95 `130 ms`, p99 `200 ms`
- `sales/service-invoices/lookup [list]`: `253` requests, average `83 ms`, median `75 ms`, p95 `120 ms`, p99 `290 ms`

Sales perf log summary from the same `August 4, 2026` run:

- `sales_invoice.list`: `613` events, average `54.70 ms`, average `29` queries, average slowest query `6.56 ms`, max request `341.21 ms`
- `sales_invoice.lookup`: `848` events, average `61.95 ms`, average `29` queries, average slowest query `15.44 ms`, max request `333.05 ms`

Conclusion:

- sales list and lookup are not currently the broad-read blocker on a fresh runtime
- the earlier broad-read slowdown should be classified alongside the older stale-runtime payables drift, not as an active sales regression
- the remaining hardening work should focus on reproducibility discipline and next-rung escalation, not emergency sales query surgery

## Purpose

This document turns SaaS Readiness Phase A into an executable sequence.

Phase A is the first serious concurrency proof layer above the current low-load validation.

It is not yet the `1000-user` claim.

It is the gate we must pass before attempting `250+` user SaaS readiness.

## Phase A Goal

Prove that Finacc remains:

- correct
- observable
- operationally stable

at `50` and `100` concurrent-user mixed SaaS baselines.

## What Phase A Should Prove

1. Authentication remains stable under larger overlap.
2. Modern lookup-heavy traffic remains healthy.
3. Purchase mixed read/write still behaves correctly at higher concurrency.
4. Existing read-heavy reporting endpoints do not collapse immediately.
5. The environment exposes the real next bottleneck clearly.

## Current Constraint

Current Locust automation is still stronger in:

- read-heavy coverage
- purchase lifecycle coverage

and weaker in:

- voucher write stress
- purchase create/save
- sales create/save
- report-under-write interference

So Phase A should be honest:

- use the best currently executable workload mix
- document what is not yet represented

## Pre-Run Checklist

Before every Phase A run, confirm:

- backend build frozen
- frontend build frozen if browser validation is also being done
- DB snapshot known
- queue/workers healthy
- Locust `.env` verified
- `FINACC_ENABLE_LIFECYCLE_TESTS=true` for write-mix runs
- target entity and seed data confirmed
- infra metric collection enabled

## Workload Mix For Phase A

Use four practical run families.

### Family 1: Read-modern baseline

Purpose:
- prove operational reads at larger concurrency

Coverage:
- sales modern lookup/navigation
- purchase modern lookup/navigation
- payables/reporting read routes
- bank reconciliation read routes

### Family 2: Purchase mixed operational

Purpose:
- prove confirmed purchase overlap does not break under larger concurrency

Coverage:
- purchase lookup
- purchase cross-mode navigation
- purchase confirm/post lifecycle

### Family 3: Purchase legacy comparison

Purpose:
- quantify how much worse legacy list/search paths behave at higher concurrency

Coverage:
- purchase legacy search routes only

### Family 4: General read baseline

Purpose:
- capture a broader system-wide low-risk concurrency picture

Coverage:
- tagged `read`

## Command Set

All commands assume:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
```

## Phase A.0 Read-Modern 50 Users

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 20m \
  --tags read-modern \
  --csv results_saas_phaseA_read_modern_50u_20m_2026_08_01 \
  --html results_saas_phaseA_read_modern_50u_20m_2026_08_01.html
```

## Phase A.1 Purchase Mixed 50 Users

```bash
FINACC_ENABLE_LIFECYCLE_TESTS=true \
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 20m \
  --tags purchase-mixed \
  --csv results_saas_phaseA_purchase_mixed_50u_20m_2026_08_01 \
  --html results_saas_phaseA_purchase_mixed_50u_20m_2026_08_01.html
```

## Phase A.2 Purchase Legacy 50 Users

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 20m \
  --tags purchase-legacy \
  --csv results_saas_phaseA_purchase_legacy_50u_20m_2026_08_01 \
  --html results_saas_phaseA_purchase_legacy_50u_20m_2026_08_01.html
```

## Phase A.3 Broad Read 50 Users

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 20m \
  --tags read \
  --csv results_saas_phaseA_read_50u_20m_2026_08_01 \
  --html results_saas_phaseA_read_50u_20m_2026_08_01.html
```

## Phase A.4 Read-Modern 100 Users

Only run this if the 50-user read-modern pass is stable.

```bash
locust -f locustfile.py --headless --users 100 --spawn-rate 10 --run-time 20m \
  --tags read-modern \
  --csv results_saas_phaseA_read_modern_100u_20m_2026_08_01 \
  --html results_saas_phaseA_read_modern_100u_20m_2026_08_01.html
```

## Phase A.5 Purchase Mixed 100 Users

Only run this if the 50-user purchase mixed pass is stable.

```bash
FINACC_ENABLE_LIFECYCLE_TESTS=true \
locust -f locustfile.py --headless --users 100 --spawn-rate 10 --run-time 20m \
  --tags purchase-modern purchase-write \
  --csv results_saas_phaseA_purchase_mixed_100u_20m_2026_08_01 \
  --html results_saas_phaseA_purchase_mixed_100u_20m_2026_08_01.html
```

## Phase A.6 Purchase Legacy 100 Users

Only run this if the 50-user legacy comparison stays controlled.

```bash
locust -f locustfile.py --headless --users 100 --spawn-rate 10 --run-time 20m \
  --tags purchase-legacy \
  --csv results_saas_phaseA_purchase_legacy_100u_20m_2026_08_01 \
  --html results_saas_phaseA_purchase_legacy_100u_20m_2026_08_01.html
```

## Phase A.7 Broad Read 100 Users

```bash
locust -f locustfile.py --headless --users 100 --spawn-rate 10 --run-time 20m \
  --tags read \
  --csv results_saas_phaseA_read_100u_20m_2026_08_01 \
  --html results_saas_phaseA_read_100u_20m_2026_08_01.html
```

## Stop Conditions

Stop escalation to the next run if any of the following occur:

- correctness defect appears
- error rate exceeds `1%`
- p95 blows past defined SLO with no recovery
- DB connections or CPU approach unsafe levels
- queue backlog grows without recovery
- app nodes show memory leak behavior

## Expected Interpretation

If Phase A results look like this:

- read-modern stable
- purchase mixed stable
- purchase legacy significantly slower
- broad read stable but heavier

then the likely next recommendation is:

- tune legacy and cross-mode hot paths
- continue toward `150 to 250` user Phase B

If Phase A fails early:

- do not move to `250`
- fix the dominant bottleneck first

## Known Gaps In Phase A

Phase A is still not a full SaaS proof yet because current Locust coverage does not yet include:

- payment/receipt write stress
- sales draft create/save stress
- purchase draft create/save stress
- report-under-write mixed interference
- export-heavy load
- onboarding/bootstrap concurrency

Those should be added before any final `500` or `1000` readiness claim.

## Result Template

## Execution Results

### Phase A.0 Read-Modern 50 Users

Executed on `2026-08-04` against validated runtime `127.0.0.1:8015`.

Artifact:
- `Finacc/perf/locust/results_saas_phaseA_read_modern_50u_20m_2026_08_04_r1_validated_runtime_stats.csv`

Result:
- requests: `29,371`
- failures: `0`
- average: `56 ms`
- median: `51 ms`
- p95: `100 ms`
- p99: `150 ms`
- max: `820 ms`
- throughput: `24.48 req/s`

Assessment:
- clean pass

### Phase A.1 Purchase Mixed 50 Users

Executed on `2026-08-04` against validated runtime `127.0.0.1:8015` with `FINACC_ENABLE_LIFECYCLE_TESTS=true`.

Artifact:
- `Finacc/perf/locust/results_saas_phaseA_purchase_mixed_50u_20m_2026_08_04_r3_seed_fix_validated_runtime_stats.csv`
- `Finacc/perf/locust/results_saas_phaseA_purchase_mixed_50u_20m_2026_08_04_r3_seed_fix_validated_runtime_failures.csv`

Result:
- requests: `63,063`
- failures: `0`
- average: `108 ms`
- median: `84 ms`
- p95: `270 ms`
- p99: `410 ms`
- max: `1288 ms`
- throughput: `52.56 req/s`

Representative endpoints:
- `purchase/purchase-invoices/lookup [list]`: `6,756` requests, `74 ms` average, `49 ms` median, `220 ms` p95, `340 ms` p99
- `purchase/purchase-service-invoices/lookup [list]`: `3,304` requests, `75 ms` average, `50 ms` median, `210 ms` p95, `370 ms` p99
- `purchase/invoices [confirm]`: `3,301` requests, `107 ms` average, `81 ms` median, `260 ms` p95, `390 ms` p99
- `purchase/service-invoices [confirm]`: `3,325` requests, `109 ms` average, `82 ms` median, `260 ms` p95, `410 ms` p99
- `purchase/invoices [draft create]`: `4,984` requests, `125 ms` average, `100 ms` median, `290 ms` p95, `420 ms` p99
- `purchase/service-invoices [draft create]`: `4,942` requests, `137 ms` average, `110 ms` median, `300 ms` p95, `460 ms` p99
- `purchase/goods-detail [seed]`: `4,989` requests, `99 ms` average, `77 ms` median, `240 ms` p95, `390 ms` p99
- `purchase/service-detail [seed]`: `4,947` requests, `100 ms` average, `77 ms` median, `240 ms` p95, `390 ms` p99

Assessment:
- clean pass after seed-helper retry hardening
- core mixed purchase business routes remained healthy with zero failures across the full 20-minute run
- next step is Phase A.3 broad read baseline

### Phase A.2 Purchase Legacy 50 Users

Executed on `2026-08-04` against validated runtime `127.0.0.1:8015`.

Artifact:
- `Finacc/perf/locust/results_saas_phaseA_purchase_legacy_50u_20m_2026_08_04_r1_validated_runtime_stats.csv`

Result:
- requests: `12,674`
- failures: `0`
- average: `1672.78 ms`
- median: `1200 ms`
- p95: `4300 ms`
- p99: `5100 ms`
- max: `6372.48 ms`
- throughput: `13.61 req/s`

Representative endpoints:
- `purchase/purchase-invoices/search [legacy]`: `7,219` requests, `1662.93 ms` average, `1200 ms` median, `4200 ms` p95, `5100 ms` p99
- `purchase/purchase-service-invoices/search [legacy]`: `5,355` requests, `1715.27 ms` average, `1300 ms` median, `4300 ms` p95, `5200 ms` p99

Assessment:
- clean pass from a correctness point of view
- clearly much slower than Phase A.1 purchase mixed on the same runtime
- legacy search is a real performance liability and should not be treated as equivalent to the modern purchase path

Comparison to Phase A.1:
- throughput dropped from `52.56 req/s` to `13.61 req/s`
- aggregate median increased from `84 ms` to `1200 ms`
- aggregate p95 increased from `270 ms` to `4300 ms`
- aggregate p99 increased from `410 ms` to `5100 ms`

### Phase A.3 Broad Read 50 Users

Official replacement executed on `Tuesday, August 4, 2026` against fresh validated runtime `127.0.0.1:8017`.

Artifact:
- [results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated_stats.csv:1)
- [results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated_failures.csv:1)
- [results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_50u_20m_2026_08_04_r2_8017_fresh_validated.html)

Result:
- requests: `29,133`
- failures: `0`
- average: `64.22 ms`
- median: `56 ms`
- p95: `120 ms`
- p99: `200 ms`
- max: `1098.52 ms`
- throughput: `24.30 req/s`

Representative endpoints:
- `reports/payables/aging [get]`: `1,507` requests, `92.37 ms` average, `74 ms` median, `200 ms` p95, `280 ms` p99
- `sales/invoices [list]`: `2,501` requests, `68.90 ms` average, `63 ms` median, `110 ms` p95, `180 ms` p99
- `sales/invoices/lookup [list]`: `2,065` requests, `73.74 ms` average, `68 ms` median, `110 ms` p95, `190 ms` p99
- `sales/service-invoices/lookup [list]`: `1,024` requests, `83.61 ms` average, `76 ms` median, `130 ms` p95, `210 ms` p99
- `sales/settings [get]`: `1,513` requests, `114.02 ms` average, `110 ms` median, `180 ms` p95, `260 ms` p99

Assessment:
- clean pass
- broad-read is now validated at `50 users / 20 minutes`
- the earlier `8015` collapse should be retained only as stale-runtime drift evidence, not as the official Phase A.3 outcome
- the next step is the next escalation rung, not additional emergency broad-read hardening

Append for each run:

### Run

- name:
- date:
- users:
- spawn rate:
- duration:
- tags:
- environment:

### Outcome

- status: `pass` / `partial` / `fail`
- p95:
- p99:
- error rate:
- max latency:

### Infra

- app CPU peak:
- app memory peak:
- DB CPU peak:
- DB memory peak:
- DB max connections:
- queue backlog:

### Findings

- 

### Action Items

- 

## Execution Update

### Run

- name: `Phase A.0 Read-Modern 50 Users`
- date: `2026-08-04`
- users: `50`
- spawn rate: `5`
- duration: `20m`
- tags: `read-modern`
- environment: `127.0.0.1:8015`, Gunicorn `4 workers / 2 threads`

Artifacts:

- [results_saas_phaseA_read_modern_50u_20m_2026_08_04_r1_validated_runtime_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_modern_50u_20m_2026_08_04_r1_validated_runtime_stats.csv:1)
- [results_saas_phaseA_read_modern_50u_20m_2026_08_04_r1_validated_runtime.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_saas_phaseA_read_modern_50u_20m_2026_08_04_r1_validated_runtime.html:1)

### Outcome

- status: `pass`
- total requests: `29371`
- failures: `0`
- error rate: `0%`
- aggregate average: `56 ms`
- aggregate median: `51 ms`
- aggregate p95: `100 ms`
- aggregate p99: `150 ms`
- max latency: `820 ms`
- throughput: about `24.48 req/s`

Endpoint highlights:

- `purchase/purchase-invoices/lookup [list]`
  - requests: `5844`
  - average: `46 ms`
  - median: `43 ms`
  - p95: `77 ms`
  - p99: `120 ms`
  - max: `720 ms`
- `sales/invoices/lookup [list]`
  - requests: `5752`
  - average: `74 ms`
  - median: `69 ms`
  - p95: `120 ms`
  - p99: `160 ms`
  - max: `820 ms`
- purchase and sales cross-mode navigation routes stayed in the `39 ms` to `47 ms` median band
- all lookup seed endpoints remained comfortably sub-`100 ms` at p95

### Infra

- app CPU peak: `not captured in this local pass`
- app memory peak: `not captured in this local pass`
- DB CPU peak: `not captured in this local pass`
- DB memory peak: `not captured in this local pass`
- DB max connections: `not captured in this local pass`
- queue backlog: `not applicable in this read-modern pass`

### Findings

- the validated `8015` runtime shape remains healthy under the broader modern read mix, not just isolated financial-report traffic
- there was no visible degradation trend across the full `20-minute` window
- lookup and cross-mode navigation paths stayed well within the current baseline targets
- this gives Phase A a trustworthy first formal rung after the recent hardening cycle

### Action Items

- proceed to `Phase A.1 Purchase Mixed 50 Users`
- keep the same validated runtime shape for the next family so results stay comparable
- continue preserving fresh-stack discipline and avoid reusing stale long-lived runtimes for formal baseline evidence
