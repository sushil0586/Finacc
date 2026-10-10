# Phase 2B.3C.1A - Docker Performance Authentication Fixture Readiness

Date: 2026-10-10  
Environment: local Docker performance stack  
Database gate: `finacc_perf_local` on Docker PostgreSQL host `postgres`  
Verdict: **Pass for authenticated read/report baseline readiness**

## Objective

Provision legitimate local-only performance users for the existing Phase 2B.3B fixture tenants without bypassing authentication, subscription membership, RBAC, tenant isolation, or accounting controls.

## Implementation

Added `entity/management/commands/provision_performance_auth.py`.

The command:

- Runs `audit_performance_staging --strict` before any write.
- Resolves the three fixture tenants by stable fixture labels:
  - `Phase2B3B small Small Tenant`
  - `Phase2B3B small Medium Tenant`
  - `Phase2B3B small Large Tenant`
- Requires the password through `FINACC_PERF_AUTH_PASSWORD` or a caller-selected env var.
- Does not print or persist passwords, tokens, or cookies.
- Creates normal active non-staff users:
  - `perf-api-small@local.invalid`
  - `perf-api-medium@local.invalid`
  - `perf-api-large@local.invalid`
- Reuses `SubscriptionService.ensure_customer_account`, `ensure_active_subscription`, and `ensure_account_membership`.
- Attaches each fixture entity to its own local-only customer account when the entity has no customer account yet.
- Creates one entity-scoped RBAC role per tenant with read/report-style permissions only.
- Assigns each user only to its own tenant.
- Captures before/after financial counts and AP/AR open balances.

## Safety Gate

Strict performance safety audit passed before provisioning.

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c1a_safety_audit_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1a_safety_audit_final_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1a_auth_dry_run_2026-10-10.json`

Final safety audit result: ready `true`, verified gates `13`, blocked gates `0`.

Dry-run resolved all three tenants and reported:

| Tenant | Entity | Entity FY | Subentity | Read/report permissions |
| --- | ---: | ---: | ---: | ---: |
| Small | 5 | 5 | 5 | 283 |
| Medium | 6 | 6 | 6 | 283 |
| Large | 7 | 7 | 7 | 283 |

## Provisioning Result

Provisioning completed successfully and was idempotent.

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c1a_auth_final_provision_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1a_auth_idempotency_final_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1a_membership_inventory_2026-10-10.txt`

Final inventory:

| User | Staff/Superuser | Membership | Entity | RBAC role |
| --- | --- | --- | ---: | --- |
| `perf-api-small@local.invalid` | No / No | viewer | 5 | `perf_read_report_baseline` |
| `perf-api-medium@local.invalid` | No / No | viewer | 6 | `perf_read_report_baseline` |
| `perf-api-large@local.invalid` | No / No | viewer | 7 | `perf_read_report_baseline` |

Idempotency rerun:

- Users already existed.
- Roles already existed.
- Assignments already existed.
- Financial counts unchanged.

## Nginx Auth Verification

Verified through the real local path:

`Nginx localhost:18080 -> Gunicorn -> Django -> PostgreSQL/Redis`

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c1a_nginx_auth_verify_final_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3c1a_docker_ps_2026-10-10.txt`

Results:

| User | Login | `/api/auth/me` | Visible tenants | Own FY | Other FY | Own sales lookup | Other sales lookup |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| Small | 200 | 200 | `[5]` | 200 | 404 | 200 | 403 |
| Medium | 200 | 200 | `[6]` | 200 | 404 | 200 | 403 |
| Large | 200 | 200 | `[7]` | 200 | 404 | 200 | 403 |

Auth cookies were issued by the real login flow. Secret cookie values and passwords were not logged.

## Financial Reconciliation

No accounting document or balance counts changed after provisioning and read-only verification.

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3c1a_financial_reconciliation_after_auth_2026-10-10.json`

Final fixture balances:

| Entity | Sales invoices | Purchase invoices | AR open | AP open |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 6 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 7 | 1,000 | 500 | 472,000.00 | 236,000.00 |

## Remaining Risks

- The command grants read/report-style permissions from the current permission catalog. If new read/report endpoints introduce write-like side effects under `view` actions, those endpoint contracts should be reviewed before broadening baseline coverage.
- This phase verified authentication and tenant isolation only. It did not run Locust load profiles.
- Password material was generated ephemerally for this run. Future reruns must provide `FINACC_PERF_AUTH_PASSWORD` through a secure local-only environment source.

## Phase 2B.3C.1 Readiness

Recommendation: **Go for authenticated Docker read/report API baseline**.

The previous blocker is closed: dedicated performance users now authenticate through the production-like local request path and are constrained to their own fixture tenants.
