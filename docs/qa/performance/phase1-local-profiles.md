# Finacc Phase 1 Local Performance Profiles

Date: 2026-10-10

These profiles are for controlled pre-launch certification. Keep write and lifecycle flows disabled unless the target database is isolated and disposable.

## Environment

- Backend root: `/Users/ansh/finacc-angular/finacc-django/Finacc`
- Locust file: `perf/locust/locustfile.py`
- Baseline probe: `perf/baseline/phase1_api_baseline.py`
- Evidence output: `docs/qa/performance/evidence/`
- Local production-style app server command:

```bash
venv/bin/gunicorn FA.wsgi:application --bind 127.0.0.1:8015 --workers 3 --timeout 120
```

## Common Safety Flags

```bash
export LOCUST_HOST=http://127.0.0.1:8015
export FINACC_ENABLE_WRITE_TESTS=false
export FINACC_ENABLE_LIFECYCLE_TESTS=false
```

## Django SQL Baseline

Use this for query counts and slow SQL samples. It is not an HTTP capacity test.

```bash
FINACC_BASELINE_USER_ID=2 FINACC_BASELINE_AS_OF_DATE=2026-10-10 \
  venv/bin/python perf/baseline/phase1_api_baseline.py \
  --label phase1_api_baseline_2026-10-10 \
  --exclude purchase/invoices
```

`purchase/invoices` is excluded in the repeatable run because the first probe exceeded the manual stop threshold and exposed a serializer/deferred-field N+1 risk.

## Local Locust Profiles

Run only after valid test credentials are configured in `perf/locust/.env`.

```bash
# 1 user smoke
venv/bin/locust -f perf/locust/locustfile.py --headless --users 1 --spawn-rate 1 --run-time 30s \
  --tags read-modern --csv docs/qa/performance/evidence/locust_read_modern_1u_30s \
  --html docs/qa/performance/evidence/locust_read_modern_1u_30s.html

# 5 users baseline
venv/bin/locust -f perf/locust/locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m \
  --tags read-modern --csv docs/qa/performance/evidence/locust_read_modern_5u_2m \
  --html docs/qa/performance/evidence/locust_read_modern_5u_2m.html

# 10 users baseline
venv/bin/locust -f perf/locust/locustfile.py --headless --users 10 --spawn-rate 2 --run-time 3m \
  --tags read-modern --csv docs/qa/performance/evidence/locust_read_modern_10u_3m \
  --html docs/qa/performance/evidence/locust_read_modern_10u_3m.html

# 25 users readiness profile, not yet executed in Phase 1 local
venv/bin/locust -f perf/locust/locustfile.py --headless --users 25 --spawn-rate 5 --run-time 5m \
  --tags read-modern,ap-ar-reports --csv docs/qa/performance/evidence/locust_read_reports_25u_5m \
  --html docs/qa/performance/evidence/locust_read_reports_25u_5m.html

# 50 users certification profile, not yet executed in Phase 1 local
venv/bin/locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m \
  --tags read-modern,ap-ar-reports,financial-reports --csv docs/qa/performance/evidence/locust_read_reports_50u_5m \
  --html docs/qa/performance/evidence/locust_read_reports_50u_5m.html
```

Do not run the 25 or 50 user profiles until Phase 1 blockers are cleared and a staging/prod-like server is available.
