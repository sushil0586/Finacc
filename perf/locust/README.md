# Finacc Django Locust Starter

This is the backend performance test starter for Finacc (`/api/*` routes).

## Covered endpoints

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/reports/payables/meta/`
- `GET /api/reports/payables/aging/`
- `GET /api/bank-reconciliation/meta/`
- `GET /api/bank-reconciliation/sessions/`
- `GET /api/sales/invoices/`
- `GET /api/sales/invoices/lookup/`
- `GET /api/sales/service-invoices/lookup/`
- `GET /api/sales/invoices/<id>/cross-mode-nav/`
- `GET /api/sales/service-invoices/<id>/cross-mode-nav/`
- `GET /api/purchase/purchase-invoices/lookup/`
- `GET /api/purchase/purchase-service-invoices/lookup/`
- `GET /api/purchase/purchase-invoices/<id>/cross-mode-nav/`
- `GET /api/purchase/purchase-service-invoices/<id>/cross-mode-nav/`
- `GET /api/sales/settings/`
- optional `PATCH /api/sales/settings/` (disabled by default)
- optional sales invoice lifecycle (`confirm`, `post`, `reverse`) (disabled by default)
- optional purchase invoice lifecycle (`confirm`, `post`) for goods and service lookup seeds (disabled by default)

## Setup

```bash
cd perf/locust
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with staging/local credentials and IDs.
You can set these either in `perf/locust/.env` or backend root `.env` (`Finacc/.env`).

Minimum values to confirm before running:

- `LOCUST_HOST`
- `FINACC_USER_EMAIL`
- `FINACC_USER_PASSWORD`
- `FINACC_ENTITY_ID`
- `FINACC_ENTITY_FIN_ID`
- optional `FINACC_SUBENTITY_ID`
- optional `FINACC_REPORT_AS_OF_DATE`

## Run

UI mode:

```bash
locust -f locustfile.py
```

Headless mode:

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m
```

Headless with report artifacts:

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m \
  --csv results_read_50u_5m --html results_read_50u_5m.html
```

Use local Django host:

```bash
locust -f locustfile.py --host http://127.0.0.1:8000
```

Recommended first ladder:

```bash
locust -f locustfile.py --headless --users 10 --spawn-rate 2 --run-time 3m \
  --tags read --csv results_read_10u_3m --html results_read_10u_3m.html

locust -f locustfile.py --headless --users 25 --spawn-rate 5 --run-time 5m \
  --tags read --csv results_read_25u_5m --html results_read_25u_5m.html

locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m \
  --tags read --csv results_read_50u_5m --html results_read_50u_5m.html
```

This keeps the first pass read-only while covering:

- auth login/session validation
- payables meta
- AP aging
- bank reconciliation meta
- bank reconciliation sessions
- sales invoice list
- sales invoice lookup
- service invoice lookup
- cross-mode sales navigation probes
- purchase invoice lookup
- purchase service invoice lookup
- cross-mode purchase navigation probes
- sales settings read

Modern operational read profile:

```bash
locust -f locustfile.py --headless --users 10 --spawn-rate 2 --run-time 3m \
  --tags read-modern --csv results_read_modern_10u_3m --html results_read_modern_10u_3m.html
```

Use this to measure the optimized UI-facing sales read paths separately from the legacy full-list compatibility endpoint.

Purchase-only modern operational read profile:

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 1m \
  --tags purchase-modern --csv results_purchase_modern_5u_1m --html results_purchase_modern_5u_1m.html
```

Use this to measure the optimized Purchase lookup and navigation paths without mixing in the Sales modern-read scenarios.

Purchase legacy compatibility profile:

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 1m \
  --tags purchase-legacy --csv results_purchase_legacy_5u_1m --html results_purchase_legacy_5u_1m.html
```

Use this to measure the older full-list Purchase search endpoints side-by-side with `purchase-modern`.

## Scope Notes

Sales endpoints use:

- `entity_id`
- `entityfinid`
- optional `subentity_id`

Payables and bank reconciliation endpoints use:

- `entity`
- `entityfinid`
- optional `subentity`

The Locust file handles this automatically, but the IDs still need to match real data in the target environment.

AP aging defaults:

- `view=summary`
- `include_trace=true`

You can override these in `.env`:

```bash
FINACC_REPORT_AS_OF_DATE=2026-04-30
FINACC_AP_AGING_VIEW=invoice
```

## Important

- Keep `FINACC_ENABLE_WRITE_TESTS=false` unless you are in a safe staging DB.
- Keep `FINACC_ENABLE_LIFECYCLE_TESTS=false` unless you are in a safe staging DB.
- Start with read-heavy scenarios, then gradually add write endpoints.
- For the first baseline, prefer `--tags read`.

## Enable Lifecycle Scenario

In `.env`:

```bash
FINACC_ENABLE_LIFECYCLE_TESTS=true
```

Then run a low load first:

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m
```

Run lifecycle-only profile (tag-based):

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m \
  --tags lifecycle --csv results_lifecycle_5u_2m --html results_lifecycle_5u_2m.html
```

## Phase 1 Write-Stress Status

Current write automation coverage in this Locust setup is limited to:

- optional `PATCH /api/sales/settings/`
- optional sales invoice lifecycle:
  - confirm
  - post
  - reverse
- optional purchase invoice lifecycle:
  - purchase invoice confirm
  - purchase invoice post
  - purchase service invoice confirm
  - purchase service invoice post

This means:

- sales write smoke is executable now
- purchase write stress is partially automated here
- voucher write stress is not yet fully automated here
- reports-under-write is only partially approximated through mixed tag runs

See:

- [finacc-stress-phase1-write-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-write-plan-2026-08-01.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)

## Auth Session Touch Note

Authenticated API requests use session-backed JWT validation. As of `2026-08-01`, backend auth was hardened so `AuthSession.last_used_at` is no longer updated on every request.

Current behavior:

- session validity is still checked on every authenticated request
- `last_used_at` is only persisted when the configured touch interval is exceeded
- default interval: `300` seconds via `AUTH_SESSION_TOUCH_INTERVAL_SECONDS`

Why this matters:

- reduces write amplification on `Authentication_authsession`
- lowers avoidable auth-path contention during read/write stress runs
- preserves revocation and expiry enforcement

Recommended first executable Phase 1 runs:

```bash
locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 5m \
  --tags lifecycle \
  --csv results_phase1_sales_write_smoke_2u_5m_2026_08_01 \
  --html results_phase1_sales_write_smoke_2u_5m_2026_08_01.html

locust -f locustfile.py --headless --users 10 --spawn-rate 2 --run-time 10m \
  --tags read-modern,lifecycle \
  --csv results_phase1_sales_mixed_10u_10m_2026_08_01 \
  --html results_phase1_sales_mixed_10u_10m_2026_08_01.html

locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 5m \
  --tags purchase-write \
  --csv results_phase1_purchase_write_smoke_2u_5m_2026_08_01 \
  --html results_phase1_purchase_write_smoke_2u_5m_2026_08_01.html
```

## Purchase Write Seed Note

Purchase lifecycle stress relies on lookup-seeded existing purchase documents.

During `2026-08-01` execution we found malformed historical purchase drafts in entity `10` where header `doc_code` values had been overwritten with runtime-like values such as `PWI298194` instead of valid purchase document-type codes like `PINV`, `PCN`, or `PDN`.

That caused false `400` failures during confirm/post stress because the backend could not resolve a matching purchase `DocumentType`.

The Locust harness now filters purchase lookup seeds to valid purchase document codes before attempting confirm/post. This keeps the purchase write baseline focused on real lifecycle behavior rather than bad seed-data noise.
