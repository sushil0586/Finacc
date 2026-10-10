# Finacc Phase 1 Performance Baseline

Date: 2026-10-10
Environment: local development, PostgreSQL, Django backend

## Scope

Phase 1 covered discovery and low-volume baseline only. No production data was modified, no accounting business logic was changed, and no high-load test was run.

## Evidence

- Django SQL/API probe: `docs/qa/performance/evidence/phase1_api_baseline_2026-10-10.json`
- Django SQL/API CSV: `docs/qa/performance/evidence/phase1_api_baseline_2026-10-10.csv`
- Locust Gunicorn smoke: `docs/qa/performance/evidence/locust_phase1_read_modern_1u_30s_2026-10-10.html`
- Locust CSV artifacts: `docs/qa/performance/evidence/locust_phase1_read_modern_1u_30s_2026-10-10*.csv`
- Reusable profiles: `docs/qa/performance/phase1-local-profiles.md`

## Server And Database Discovery

- Local port `127.0.0.1:8000` is running `manage.py runserver`; it was not used as a capacity target.
- Production deployment reference is Gunicorn: `FA.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120`.
- Local Gunicorn 23.0.0 is available and was started briefly on `127.0.0.1:8015` for a 1-user smoke.
- Django `DEBUG=False`.
- Database: PostgreSQL 16.12, database `finacc_db`, host `127.0.0.1`, `CONN_MAX_AGE=0`, health checks enabled.
- DB pool is disabled locally.
- Cache backend is local memory. `META_CACHE_ENABLED=False` and `PAYABLES_META_CACHE_ENABLED=False`.
- PostgreSQL `max_connections=100`, `shared_buffers=128MB`.

## Data Shape

Largest local tables by estimated live rows:

- `auditlogger_auditlog`: 5,749,574
- `rbac_rolepermission`: 536,063
- `posting_journalline`: 180,035
- `purchase_purchaseinvoiceheader`: 70,891
- `purchase_purchaseinvoiceline`: 64,807
- `posting_postingbatch`: 55,100
- `posting_entry`: 51,164
- `purchase_purchasetaxsummary`: 49,085
- `purchase_vendorbillopenitem`: 46,329
- `sales_invoice_header`: 30,135

## Priority API Baseline

Single-user Django-side probe with SQL capture. This measures endpoint code path and DB work, not external HTTP capacity.

| API | Status | Time ms | Queries | SQL ms |
|---|---:|---:|---:|---:|
| `reports/payables/vendor-outstanding` | 200 | 7440.61 | 42 | 408.00 |
| `reports/receivables/open-items` | 200 | 6833.50 | 37 | 549.00 |
| `sales/invoices` | 200 | 4657.96 | 31 | 191.00 |
| `reports/financial/daybook` | 200 | 3004.64 | 34 | 2933.00 |
| `reports/receivables/aging` | 200 | 1750.89 | 37 | 198.00 |
| `reports/financial/trial-balance` | 200 | 793.13 | 36 | 281.00 |
| `reports/payables/aging` | 200 | 665.33 | 41 | 326.00 |
| `reports/financial/ledger-summary` | 200 | 643.78 | 34 | 226.00 |
| `reports/receivables/customer-outstanding` | 200 | 540.72 | 42 | 217.00 |
| `reports/gstr1/summary` | 200 | 456.23 | 37 | 383.00 |
| `reports/payables/meta` | 200 | 164.51 | 31 | 79.00 |
| `payments/vouchers-lookup` | 200 | 117.05 | 18 | 57.00 |
| `receipts/vouchers-lookup` | 200 | 107.39 | 18 | 48.00 |
| `sales/service-invoices-lookup` | 200 | 89.97 | 31 | 52.00 |
| `sales/invoices-lookup` | 200 | 69.97 | 31 | 30.00 |
| `dashboard/home-meta` | 200 | 66.62 | 41 | 36.00 |
| `purchase/invoices-lookup` | 200 | 58.97 | 17 | 42.00 |
| `purchase/service-invoices-lookup` | 200 | 49.44 | 17 | 28.00 |
| `auth/me` | 200 | 37.64 | 17 | 22.00 |
| `purchase/invoices` | SKIPPED | n/a | n/a | n/a |

`purchase/invoices` was attempted first and manually stopped after exceeding the Phase 1 probe threshold. Stack trace showed repeated model `refresh_from_db()` calls during serializer field access, indicating deferred-field/N+1 behavior.

## Locust Smoke

Executed against local Gunicorn on `127.0.0.1:8015`:

```bash
LOCUST_HOST=http://127.0.0.1:8015 FINACC_ENABLE_WRITE_TESTS=false FINACC_ENABLE_LIFECYCLE_TESTS=false \
  venv/bin/locust -f perf/locust/locustfile.py --headless --users 1 --spawn-rate 1 --run-time 30s --tags read-modern
```

Result: not passed. The stored Locust credentials returned `403 invalid_credentials`, then all protected GETs returned `401`. This validates harness startup but does not validate authenticated HTTP performance.

## Findings

### P0

- `purchase/invoices` full list endpoint is not certifiable yet. Even with `page_size=25`, it exceeded the manual Phase 1 stop threshold and the stack trace points to serializer access of deferred fields causing repeated `refresh_from_db()` calls.
- Locust authenticated HTTP baseline is blocked because `perf/locust/.env` credentials are invalid. No Locust performance result should be treated as passed until valid isolated test credentials are prepared.

### P1

- `reports/payables/vendor-outstanding` took 7.44s with only 408ms captured SQL, so most time is likely Python-side processing, serialization, iteration, or hidden cursor/object work.
- `reports/receivables/open-items` took 6.83s with 549ms captured SQL. It includes a slow distinct invoice-line query and likely has additional Python aggregation overhead.
- `sales/invoices` took 4.66s for 25 rows. This is too slow for an invoice search/list UX and should be reviewed for serializer shape, deferred fields, joins, and response payload size.
- `reports/financial/daybook` took 3.00s, with 2.93s SQL time. This is the clearest SQL-bound report in the baseline.

### P2

- Local DB connection persistence is off (`CONN_MAX_AGE=0`) and DB pooling is disabled. This is acceptable for discovery, but staging/prod certification should use the intended production connection policy.
- Local memory cache disables shared cache behavior and payables meta cache. Report timings may improve or change materially with Redis/shared cache.
- Large audit/RBAC tables are present locally. Audit cleanup/partitioning and RBAC permission-cache strategy should be reviewed before larger load tests.

## Next Actions Before Phase 2

1. Fix or replace Locust credentials with an isolated test user that has entity `10`, FY `8`, and subentity `8` access.
2. Optimize `purchase/invoices` serializer/queryset before rerunning the complete 20-API probe.
3. Profile `vendor-outstanding`, `receivables/open-items`, `sales/invoices`, and `daybook` with Django Debug Toolbar/Silk or targeted cProfile to split DB time from Python serialization time.
4. Review indexes and query plans for daybook, posting journal lines, vendor bill open items, sales invoice headers/lines, and tax summaries.
5. Re-run Phase 1 1-user authenticated Locust smoke on Gunicorn, then proceed to 5 and 10 users only after P0s are cleared.
