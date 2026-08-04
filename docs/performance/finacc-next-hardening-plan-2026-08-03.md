# Finacc Next Hardening Plan

Last updated: 2026-08-04

Status: active execution plan for the next stress-hardening cycle

Related documents:
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [finacc-saas-phaseA-100-user-baseline-execution-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-saas-phaseA-100-user-baseline-execution-2026-08-01.md:1)
- [financial-reports-performance-stress-plan-2026-08-02.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/financial-reports-performance-stress-plan-2026-08-02.md:1)
- [local-postgres-stress-prerequisites-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/local-postgres-stress-prerequisites-2026-08-03.md:1)
- [payables-runtime-comparison-checklist-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/payables-runtime-comparison-checklist-2026-08-03.md:1)

## Purpose

This document turns the current stress-testing findings into a concrete next-hardening sequence.

The immediate goal is not to broaden scope.

The immediate goal is to close the strongest remaining performance and operational risks that still block a clean `100-user` readiness story.

## Current Position On 2026-08-03

Current status by workload family:

- purchase write: materially improved and functionally clean in recent reruns
- sales write: functionally clean in recent reruns
- voucher mixed: functionally clean in recent reruns
- receivables reports: healthy at `100 users`
- payables reports: environment-sensitive; earlier `8010` runs were tail-heavy, but clean instrumented `8011` gunicorn rerun was healthy at `100 users`
- payables report fast behavior reproduced again on fresh clean `threads=2` gunicorn stack
- financial reports: correctness-safe, query counts reduced sharply, and now validated as healthy on the preferred `4 workers / 2 threads` runtime shape during the full `50-user / 15-minute` peak rerun
- consolidated SaaS Phase A: planned but not yet fully closed with one formal pass set

This means the next hardening cycle should stay focused on:

1. payables environment comparison and reproducibility closure
2. infra hygiene for meaningful higher-tier reruns
3. consolidated Phase A execution on the validated financial-report runtime shape
4. broader report-matrix expansion after the above improve

## Immediate Next Action

Start with a focused payables reproducibility pass.

Use this exact first objective:

- identify what runtime or environment difference made the older `8010` payables runs much slower than the fresh clean `8011` and `8012` stacks
- confirm whether the remaining payables risk is runtime drift rather than a still-hidden selector bottleneck

Capture at minimum:

- endpoint-level query counts
- slow SQL or slow selector blocks for `reports/payables/aging [get]`
- slow SQL or slow selector blocks for `reports/payables/meta [get]`
- enough runtime context to explain why `8010` diverged from the newer clean stacks

Do not optimize multiple areas before this first payables reproducibility result is written down.

### Realistic Payables Reproducibility Workflow

Use the same payables report stress family that exposed the earlier tail, but compare it against the cleaner fresh-stack runtime conditions that have already behaved well.

Preferred runtime shape:

- run Django on `gunicorn`
- preserve a fresh clean stack
- keep the first comparison rerun comparable to the earlier `100-user / 45-second` payables evidence

Suggested backend runtime:

```bash
cd Finacc
source venv/bin/activate
PAYABLES_PERF_LOGGING=true gunicorn FA.wsgi:application --bind 127.0.0.1:8011 --workers 4 --threads 8 --timeout 120
```

Suggested Locust rerun:

```bash
cd Finacc
source venv/bin/activate
LOCUST_HOST=http://127.0.0.1:8011 \
venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r14_repro_check \
  --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_04_r14_repro_check.html
```

Primary artifact to inspect after the run:

- [payables_perf.log](/Users/ansh/finacc-angular/finacc-django/Finacc/logs/payables_perf.log:1)

Read the log in this order:

1. `ap_aging.api_get`
2. `ap_aging.builder`
3. `ap_aging.cache_lookup`
4. `ap_aging.user_meta`
5. `payables_meta.api_get`
6. `payables_meta.builder`

Questions to answer from the log:

- which block scales worst under the real payables report concurrency?
- is the stressed tail mostly inside `ap_aging` or `payables_meta`?
- does the slow behavior reproduce on a fresh clean stack?
- if not, which runtime factor best explains the earlier `8010` divergence?

Observed update on `2026-08-03`:

- the clean `gunicorn` rerun on `127.0.0.1:8011` with `PAYABLES_PERF_LOGGING=true` was healthy at `100 users`
- `reports/payables/aging [get]` averaged about `55 ms`
- `reports/payables/meta [get]` averaged about `34 ms`
- no heavy tail similar to the earlier `8010` runs appeared
- a second clean rerun on `127.0.0.1:8012` with `--threads 2` was also healthy at `100 users`
- this means the old slow `8010` behavior is not explained by thread count alone

This changes the next question.

The next payables step is no longer only "which query is slow?".

The next payables step is:

- what runtime or environment difference made the earlier `8010` runs much slower than the clean `8011` rerun?

Immediate comparison targets:

1. runtime process model on `8010` versus `8011`
2. auth/session behavior on each stack
3. cache warmth and cache lifecycle on each stack
4. DB connection / pooling / request routing differences
5. whether the earlier server was carrying stale or unrelated pressure

Updated interpretation after the `8012` rerun:

- the clean stack stays healthy with both `threads=8` and `threads=2`
- the simple `threads` explanation is not supported
- the next payables environment task should focus on stale runtime state, cache/process drift, or surrounding load on the older `8010` server

If the clean rerun result reproduces consistently, do not keep treating payables as the top pure query-optimization blocker. Shift the payables track toward environment comparison and reproducibility first.

## Hardening Principles

Use these rules during this cycle:

- do not widen the stress matrix before current bottlenecks are better understood
- do not treat local DB saturation as a pure module defect
- keep correctness protection above throughput gains
- prefer one targeted optimization plus one same-tier rerun over many speculative code changes
- keep all reruns comparable by preserving tag set, duration, and concurrency unless the goal explicitly changes

## Priority Order

Observed financial runtime update on `2026-08-04`:

- the valid full `50-user / 15-minute` financial rerun on `127.0.0.1:8015` completed with `0` failures
- aggregate median was about `960 ms`
- aggregate p95 was about `2100 ms`
- aggregate max was about `3512 ms`
- aggregate throughput was about `16.35 req/s`
- builder timings stayed around `382 ms` with about `3` queries per call
- this confirms that the earlier `8014` slowdown was primarily runtime-shape pressure, not a re-emerging report-query explosion

## Priority 1: Payables Report Reproducibility

Why first:

- payables now looks like the most important unresolved reproducibility question
- financial reports have a validated healthier local runtime shape
- the next highest-value work is to explain why old `8010` behavior drifted so far from newer clean stacks

Current observed signals from `2026-08-04`:

- earlier payables `8010` runs were tail-heavy
- fresh clean `8011` and `8012` stacks were both healthy
- thread count alone did not explain the old slow behavior
- financial reports are now validated on `8015`, so payables reproducibility becomes the next main unknown
- a new like-for-like rerun on `2026-08-04` kept `8010` slower than `8011`
- `8010` delivered about `36.72 req/s` at about `756 ms` average and `230 ms` median
- `8011` delivered about `44.40 req/s` at about `266.86 ms` average and `120 ms` median
- `8011` payables perf logging showed light query counts and mostly cache-backed behavior, which weakens the case for a broad payables code-path defect
- a fresh same-shape replacement on `8016` delivered about `49.38 req/s` at about `64.41 ms` average and `42 ms` median
- this confirms the older `8010` slowdown is stale-runtime or environment-drift evidence, not an active payables module bottleneck

### Payables hardening tasks

1. Compare the `8010`, `8011`, and `8012` runtime setups
- server command shape
- env vars
- cache state
- surrounding process pressure

2. Preserve the payables perf logging path
- keep `PAYABLES_PERF_LOGGING` available for repeatable reruns
- use [analyze_payables_perf_log.py](/Users/ansh/finacc-angular/finacc-django/Finacc/Scripts/analyze_payables_perf_log.py:1) after each run

3. Only if the slow behavior reproduces on a fresh clean stack, return to selector/query optimization
- `all_last_payment_dates`
- `asof_advances`
- `vendor_queryset`
- request-meta overhead

4. Re-run the same payables tier when a runtime difference or code change is isolated
- keep the `100-user / 45-second` tag set comparable

5. Preserve the fresh-stack evidence
- keep the fresh same-shape comparison artifacts
- use them as the baseline reference if old local stacks drift again

### Payables exit criteria

- `0 failures`
- payables result is reproducible across the intended runtime shape
- any slow/fast divergence between server setups is explainable
- if a bottleneck remains, it is clearly classified as code-path or environment-path, not ambiguous

Immediate payables decision after the `2026-08-04` comparison:

- do not return to deeper payables selector optimization
- treat the older `8010` result as stale-runtime evidence
- keep `8011` and the fresh `8016` result as the meaningful baseline for current payables health

## Priority 2: Consolidated Phase A Rerun On Validated Runtime Shapes

Why second:

- financial reports now have a validated local peak runtime shape
- payables now also have validated healthy fresh-stack behavior
- that removes one major blocker from the broader mixed-workload story
- the next best confidence gain after payables reproducibility is a consolidated rerun using the healthier shape

### Consolidated rerun tasks

1. Reuse the validated `8015` style runtime shape for financial-heavy paths

2. Reuse a fresh clean payables stack, not the stale historical `8010` runtime

3. Re-run the consolidated SaaS Phase A matrix with comparable settings

4. Record whether the healthier financial and payables shapes improve the mixed-workload story materially

### Consolidated rerun exit criteria

- `0 failures`
- no major financial-report-driven tail collapse
- Phase A story stays consistent with the newer isolated-module evidence

## Priority 3: Financial Report Deeper Optimization If Needed

Why third:

- only needed if the full `8015` confirmation still degrades materially
- the code-path is already much cleaner than before
- runtime-shape confirmation is cheaper and higher-signal than immediate deeper refactoring

### Financial report hardening tasks if `8015` still regresses

1. Profile grouped report variants
- `trial-balance [grouped]`
- `ledger-summary [grouped]`
- compare grouped cost to base read cost

2. Profile CSV export endpoints
- measure query count and serialization cost
- identify whether repeated data shaping or export formatting dominates

3. Check request-overhead versus report-build cost
- validate whether the tail is inside the report logic or around auth/session/scope/meta work

4. Tighten the slowest path first
- choose one endpoint family with the clearest tail contribution
- make one targeted optimization before broad refactors

5. Re-run the same peak tier
- rerun `50-user / 15-minute` financial-report peak after the targeted fix

### Financial report deeper-optimization exit criteria

- `0 failures`
- aggregate latency is materially below the current slow-shape results
- multi-second extreme spikes are materially reduced
- grouped and export paths no longer show disproportionate tail cost

## Priority 3: Local Infra Hygiene For High-Tier Reruns

Why this stays in the plan:

- local Postgres and dev-server limits can distort `100-user` write-heavy interpretation
- August 3 evidence already showed connection-ceiling risk on local higher-tier write runs

### Infra tasks before any higher-tier write rerun

1. confirm `max_connections`
2. run under `gunicorn` instead of `runserver`
3. enable bounded DB pooling when using local Postgres for stress reruns
4. confirm whether PgBouncer or a staging-like stack is available for cleaner `100+` user evidence

### Infra interpretation rule

If a rerun fails with:

- `too many clients already`
- auth-path failures before business logic
- broad saturation unrelated to one module

then classify the result first as an infra-capacity signal, not immediately as an app regression.

## Priority 4: Consolidated SaaS Phase A Closure

Do this only after payables and financial-report hardening make the current picture cleaner.

The Phase A objective is still valid:

- prove operational stability at `50` and `100` concurrent users
- convert scattered module evidence into one decision-ready baseline

### Phase A closure tasks

Run the planned families from the Phase A execution doc:

1. read-modern `50 users`
2. purchase mixed `50 users`
3. purchase legacy `50 users`
4. broad read `50 users`
5. read-modern `100 users`
6. purchase mixed `100 users`
7. purchase legacy `100 users`
8. broad read `100 users`

### Phase A closure criteria

- no correctness defects
- error rate stays under the defined threshold
- p95 stays within acceptable interpretation for each family
- the next bottleneck is clear and bounded
- evidence is documented in one place for go / no-go review

## Suggested Execution Sequence

Use this order unless a new correctness defect interrupts the plan:

1. payables profiling
2. payables focused optimization
3. payables same-tier rerun
4. financial-report profiling
5. financial-report focused optimization
6. financial-report same-tier rerun
7. validate local infra settings for any new high-tier write reruns
8. execute consolidated Phase A families
9. review readiness for `150 to 250` user Phase B

## Evidence Required After Each Step

After every optimization and rerun, capture:

- code change summary
- exact command executed
- environment notes
- total requests
- failures
- average
- median
- p95
- p99
- max latency
- key endpoint breakdown
- interpretation
- explicit rerun decision

## Decision Rules

Use these go / no-go rules for the cycle:

- if correctness fails, stop and fix correctness first
- if latency improves but the tail remains materially heavy, continue profiling before broadening scope
- if infra limits dominate, fix environment hygiene before comparing module deltas
- if payables and financial reports both stabilize, proceed to formal Phase A closure
- do not move to `150+` user expansion while current `100-user` weak points are still unresolved

## Expected Outcome Of This Cycle

If this plan succeeds, we should end the cycle with:

- payables in a meaningfully cleaner `100-user` state
- financial reports in a meaningfully cleaner `50-user` peak state
- fewer ambiguous local-infra stress results
- a formal Phase A execution path that can be completed with confidence
- a clearer go / no-go answer for the next SaaS readiness tier
- financial report instrumentation and reruns on `2026-08-03` proved that the earlier `600+` query explosion was real and fixable
- the current remaining bottleneck is no longer query explosion; it is sustained peak-latency and throughput pressure even after the query collapse

Current observed signals from `2026-08-03`:

- short `50-user / 2-minute` probes improved materially after the financial query-collapse and selector-cache passes
- the full `50-user / 15-minute` rerun on `127.0.0.1:8014` still finished with `0` failures but settled around `10s` median response times across the covered report family
- financial-report perf logging showed builder averages around `1.8s` with:
  - trial balance: about `5` queries
  - ledger summary: about `8` queries
- this means the remaining pain is no longer dominated by request count explosion or request wrapper overhead

### Financial report hardening tasks

1. Treat the current problem as a sustained-concurrency throughput issue, not as another deferred-field query storm

2. Focus next profiling on the aggregate SQL and concurrency behavior of:
- movement aggregation
- posted-opening aggregation
- ledger materialization

3. Compare report behavior under smaller worker/thread shapes versus current gunicorn settings
- verify whether the current local stack is saturating on DB, worker scheduling, or both

4. Do not broaden to more financial report families until Phase R1 peak is materially healthier

### Financial report exit criteria

- full `50-user / 15-minute` R1 peak rerun remains at `0` failures
- median and tail latency come down materially from the current `~10s` median band
- remaining bottleneck is either reduced to an acceptable known ceiling or isolated clearly enough for targeted infra or SQL action
