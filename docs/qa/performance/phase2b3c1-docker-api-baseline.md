# Finacc Phase 2B.3C.1 - Docker Authenticated API Baseline And Read/Report Smoke Certification

Date: 2026-10-10  
Scope: authenticated read/report baseline gate against Docker full-small fixture  
Verdict: **Fail - authenticated baseline blocked by missing authorized performance users**

## Objective

Establish trustworthy authenticated API and reporting baselines against the Docker `finacc_perf_local` full-small dataset before concurrent load testing.

This phase intentionally allowed only read-only API requests. No fixture reset, reseed, financial write, lifecycle API, Locust concurrent profile, or accounting-rule change was performed.

## Environment Verification

Docker services were running:

```text
postgres healthy on local port 15432
redis healthy on local port 16379
web healthy on local port 18000
nginx running on local port 18080
```

PostgreSQL identity:

```text
current_database = finacc_perf_local
current_user = finacc_perf
db_size_bytes = 102,276,119
```

Strict safety audit:

```text
ready = true
verified_count = 13
blocked_count = 0
```

Fixture counts were unchanged from Phase 2B.3B.2:

```text
P2B3B-SMALL-S: 1,000 sales, 500 purchase, sales_total=590,000.00, purchase_total=295,000.00, AR open=472,000.00, AP open=236,000.00
P2B3B-SMALL-M: 1,000 sales, 500 purchase, sales_total=590,000.00, purchase_total=295,000.00, AR open=472,000.00, AP open=236,000.00
P2B3B-SMALL-L: 1,000 sales, 500 purchase, sales_total=590,000.00, purchase_total=295,000.00, AR open=472,000.00, AP open=236,000.00
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3c1_auth_inventory_2026-10-10.json
docs/qa/performance/evidence/phase2b/phase2b3c1_nginx_auth_probe_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3c1_resource_snapshot_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3c1_safety_audit_2026-10-10.json
```

## Request Path Smoke

Nginx health endpoint:

```text
GET http://localhost:18080/healthz
HTTP 200
body: ok
```

Unauthenticated auth endpoint:

```text
GET http://localhost:18080/api/auth/me
HTTP 401
{"detail":"Authentication credentials were not provided."}
```

This confirms the Nginx to Django/Gunicorn request path is reachable and the API correctly requires authentication.

Redis check:

```text
redis-cli -n 1 ping
PONG
```

PostgreSQL activity snapshot:

```text
total_connections = 1
active = 1
idle_in_tx = 0
waiting = 0
ungranted_locks = 0
```

Resource snapshot:

```text
finacc-nginx-1      0.03%     9.77MiB / 7.748GiB
finacc-postgres-1   1.19%     190.2MiB / 7.748GiB
finacc-redis-1      0.34%     10.31MiB / 7.748GiB
finacc-web-1        154.63%   465.1MiB / 7.748GiB
```

## Authentication Gate

Dedicated performance user readiness failed.

Observed users:

```json
[
  {
    "id": 1,
    "email": "perf-fixture@local.invalid",
    "username": "perf-fixture",
    "is_active": true,
    "last_login": null
  }
]
```

Observed tenant access:

```json
[]
```

There is no confirmed login-capable performance user with tenant memberships/permissions for entity IDs 5, 6, and 7. The fixture generator created the actor user used for data ownership, but not a dedicated API user with known credentials and tenant authorization.

Because this phase explicitly required read-only API requests, the certification did **not** create users, set passwords, grant memberships, issue synthetic tokens, or bypass permissions. Benchmarking authenticated endpoints under those conditions would be misleading.

## Critical Endpoint Inventory

The existing Locust framework and API routing identify these read/report endpoint families as the baseline targets once auth is available:

| Area | Representative endpoints |
| --- | --- |
| Auth | `/api/auth/login`, `/api/auth/me` |
| Sales | `/api/sales/invoices/`, `/api/sales/invoices/lookup/`, `/api/sales/service-invoices/lookup/` |
| Purchase | `/api/purchase/purchase-invoices/`, `/api/purchase/purchase-invoices/search/`, `/api/purchase/purchase-invoices/lookup/`, `/api/purchase/purchase-service-invoices/lookup/` |
| Payables | `/api/reports/payables/meta/`, `/api/reports/payables/aging/`, `/api/reports/payables/vendor-outstanding/` |
| Receivables | `/api/reports/receivables/customer-outstanding/`, `/api/reports/receivables/open-items/`, `/api/reports/receivables/aging/`, `/api/reports/receivables/collections-history/` |
| Financial reports | `/api/reports/financial/meta/`, `/api/reports/financial/trial-balance/`, `/api/reports/financial/ledger-summary/`, `/api/reports/financial/ledger-book/`, `/api/reports/financial/daybook/` |
| Dashboard / operations | `/api/dashboard/`, bank reconciliation meta/sessions |
| GST | `/api/gst-reconciliation/`, report GST datasets where applicable |

No p50/p95/p99 baseline is reported for these endpoints in Phase 2B.3C.1 because authenticated access was not available.

## Baseline Measurement Status

| Requirement | Status | Notes |
| --- | --- | --- |
| Docker services | Verified | All required containers running |
| DB identity | Verified | `finacc_perf_local` |
| Strict safety audit | Verified | 13/13 gates passed |
| Fixture counts | Verified | 4,500-invoice dataset intact |
| Nginx to API path | Verified | `/healthz` 200, `/api/auth/me` 401 without credentials |
| Redis readiness | Verified | `PONG` |
| Dedicated API users | **Failed** | No authorized login-capable performance users |
| Authenticated endpoint p50/p95/p99 | **Blocked** | Would require user/membership/password setup |
| SQL query counts/timings | **Blocked** | Not meaningful without authenticated endpoint execution |
| Response contracts/pagination/filters | **Blocked** | Not meaningful without authenticated endpoint execution |
| Tenant isolation via API | **Blocked** | No authorized user to test tenant-scoped reads |
| Financial reconciliation after reads | Not applicable | No authenticated read suite executed; precheck fixture totals unchanged |

## Comparison With Phase 1

No latency comparison is made in this phase. Phase 1 and Phase 1A/1C baselines were measured against earlier local datasets and server conditions. Phase 2B.3C.1 stopped before authenticated API execution, so claiming p50/p95/p99 comparisons would be inaccurate.

## Required Remediation Before Phase 2B.3C.1 Retry

Add a safety-gated command or fixture step that creates dedicated read-only performance API users without production credentials:

- one or more users with known local-only test passwords stored outside source control;
- active subscription/customer account membership;
- `UserEntityAccess` for each fixture tenant entity;
- RBAC permissions for read/report endpoints only;
- explicit scope IDs for entity, entityfinid, and subentity;
- no write/lifecycle permissions unless a later phase explicitly enables them;
- safety audit guard requiring `finacc_perf_local` and `postgres`.

After that, rerun:

1. Login through `/api/auth/login`.
2. Validate `/api/auth/me`.
3. Execute bounded repeated read/report probes through `http://localhost:18080`.
4. Capture p50/p95/p99, response sizes, HTTP errors, PostgreSQL activity, and financial reconciliation.

## Phase 2B.3C.1 Verdict

**Fail.**

The Docker environment and fixture dataset are healthy, but authenticated API baseline certification cannot proceed without authorized performance users. This is a readiness blocker, not an endpoint performance failure.

Do not proceed to Phase 2B.3C.2 concurrent load until this auth/membership gate is closed and Phase 2B.3C.1 is rerun successfully.
