# Finacc SaaS Phase A 100-User Baseline Execution

Last updated: 2026-08-01

Status: executable plan prepared

Related documents:
- [finacc-saas-1000-user-readiness-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-saas-1000-user-readiness-plan-2026-08-01.md:1)
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [perf/locust/README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md:1)

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
  --tags purchase-modern purchase-write \
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
