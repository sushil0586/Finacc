# Backend Performance Baseline Runbook (Finacc Django)

## Goal

Produce a first baseline with latency and error-rate metrics for core sales flows.

## Step 1: Start API in a staging-like mode

Use your normal command to run Django (`gunicorn` preferred for realistic behavior) and ensure `/api/auth/login` works.

## Step 2: Run baseline Locust profile

```bash
cd perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 3m
```

Then run:

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m
```

Recommended (persist artifacts):

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m \
  --csv results_read_50u_5m --html results_read_50u_5m.html
```

Capture:
- p50 / p95 / p99 latency
- request count and RPS
- failure count per endpoint

## Step 3: If p95 is high, inspect quickly

- check DB query count and slow queries for:
  - `/api/sales/invoices/`
  - `/api/sales/settings/`
- look for N+1 in serializers/views
- verify index usage for entity/subentity scoped filters

## Step 4: Report format

For each run, record:
- date/time
- environment (local/staging)
- users/spawn-rate/run-time
- per-endpoint p95
- top 3 slowest endpoints
- top 3 erroring endpoints

## Step 5: Decide next optimization batch

Pick one backend fix at a time, rerun same scenario, and compare p95 and error-rate deltas.

## Step 6: Lifecycle/Write Profile (Staging First)

Enable write tests only in safe environments:

```bash
export FINACC_ENABLE_LIFECYCLE_TESTS=true
```

Run low-load lifecycle-only profile:

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m \
  --tags lifecycle --csv results_lifecycle_5u_2m --html results_lifecycle_5u_2m.html
```
