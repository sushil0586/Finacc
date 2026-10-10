# Finacc Phase 2B.1 - Production-Like Staging Performance Environment Readiness

Date: 2026-10-10  
Scope: readiness assessment only; no high-volume load executed  
Verdict: **No-Go until staging isolation and telemetry are verified on the staging host**

## Objective

Prepare a safe, observable, production-like staging environment for controlled multi-tenant load testing after Phase 1 local performance remediation and Phase 2A financial write-concurrency certification.

This phase does not certify capacity. It defines the environment gate and confirms which pieces are present in the repository versus which must be verified or provisioned before Phase 2B controlled staging execution.

## Inputs Reviewed

- `docs/qa/performance/phase1-baseline-report-2026-10-10.md`
- `docs/qa/performance/phase1a-remediation-report.md`
- `docs/qa/performance/phase1b-local-load-report.md`
- `docs/qa/performance/phase1c-heavy-report-remediation.md`
- `docs/qa/performance/phase1d-final-local-certification.md`
- `docs/qa/performance/phase2a-financial-write-concurrency-certification.md`
- `FA/settings.py`
- `deploy/ec2/gunicorn.service`
- `deploy/ec2/nginx-staging.conf`
- `deploy/ec2/deploy_backend_staging.sh`
- `deploy/ec2/deploy_frontend_staging.sh`
- `perf/locust/locustfile.py`
- `perf/locust/README.md`
- `perf/baseline/phase1d_resource_monitor.py`
- Angular config under `/Users/ansh/finacc-angular/accountproject`

## Actual Configuration Inventory

| Area | Observed configuration | Readiness implication |
| --- | --- | --- |
| Django app | `FA.settings`, PostgreSQL backend, JWT auth, DRF, audit/error middleware | Good baseline; staging `.env` must be audited before load |
| App server | Gunicorn service binds `127.0.0.1:8000`, `--workers 3`, `--timeout 120` | Production-like enough for first staging gate if host CPU/RAM matches target profile |
| Reverse proxy | Nginx serves Angular assets and proxies `/api/` to Gunicorn | Good; must confirm real staging hostname/TLS and request timeout settings |
| Database | PostgreSQL via env `DB_*`; default `CONN_MAX_AGE=0`; optional psycopg pool flags | Staging DB max connections/pooling must be sized before 25/50-user tests |
| Cache | Redis optional via `CACHE_BACKEND=redis`; default locmem disables metadata caches across workers | Staging should use Redis if multi-worker metadata/report caches are enabled |
| Background jobs | systemd timers for platform approval/access expiry; no Celery worker config found | Load plan should monitor timers; async GST recon is disabled by default |
| Frontend | Angular 21 app; production build via `ng build`; Nginx static serving | Good; frontend load should be separate from API load unless browser tests are required |
| External GST | Whitebooks sandbox defaults; live GSTR flags default `False` | Staging must explicitly prove all live filing flags are false |
| Email | SMTP defaults to Gmail unless overridden | Staging must use console/file/dummy backend or controlled mailbox |
| Banking/payments | Bank reconciliation and payment voucher APIs exist; no external payment provider config verified here | Staging must prove no real bank/payment rails are reachable |
| Telemetry | `phase1d_resource_monitor.py` captures Gunicorn/Locust process metrics and PostgreSQL activity/locks | Reusable; needs staging host process patterns and DB permissions verified |
| Locust | Mixed read/report/write tags; write/lifecycle disabled unless env enables them | Good; Phase 2B must start read-only and explicitly gate writes |

## Local Evidence From This Readiness Pass

No high-volume load was executed.

PostgreSQL local snapshot after harness execution:

```text
pg_config ('finacc_db', '100', '128MB', '4MB')
pg_activity active=1 idle_in_transaction=0 waiting=0
ungranted_locks=0
db_conflicts=0 deadlocks=0
```

Phase 2A harness rerun after adding journal API-level coverage:

```bash
venv/bin/python manage.py test perf.tests_phase2a_write_concurrency --keepdb
```

Result:

```text
Ran 10 tests in 81.121s
OK
```

New journal certification coverage:

- Real `/api/vouchers/vouchers/` create API.
- Real `/api/vouchers/vouchers/<id>/confirm/` action.
- Real `/api/vouchers/vouchers/<id>/post/` action.
- 2, 5, and 10 worker concurrent journal voucher create/confirm/post workflow.
- Unique voucher numbers in the actual journal voucher series scope.
- Posted status persisted.
- Debit/credit totals equal `100.00`.
- Posting journal entries balanced for each generated voucher code.

## Expected Production-Like Infrastructure To Confirm

Minimum required before Phase 2B controlled staging load:

| Component | Required confirmation |
| --- | --- |
| App host | vCPU count, RAM, disk type, disk free space, OS limits, open files |
| Gunicorn | worker count, worker class, timeout, max requests/recycle policy, service name, logs |
| PostgreSQL | host separation, version, max connections, shared buffers, work mem, effective cache size, disk free space |
| Pooling | either no pooling with safe connection budget, or documented Django/pgBouncer/psycopg pool settings |
| Cache | Redis endpoint and TTL policy if caches are enabled; no locmem-only multi-worker cache assumptions |
| Frontend | production Angular build served by Nginx; static cache headers verified |
| Background jobs | all timers/workers listed; no unobserved write jobs during test windows |
| Network | staging URL, TLS, Nginx proxy timeouts, upstream failures visible in logs |
| External services | GST filing, email, banking/payment, production APIs blocked or sandboxed |

## Dedicated Staging Environment Gate

The repository has EC2 staging deployment scripts, but this readiness pass did not SSH into or provision staging. Therefore staging is **not yet certified ready**.

Required staging isolation checks:

1. `DEBUG=False`.
2. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` match staging only.
3. `DB_NAME` is a staging/disposable database, not production.
4. DB user has no production access.
5. `WHITEBOOKS_SANDBOX_MODE=True`.
6. `MASTERGST_ENV` and `SALES_MASTERGST_ENV` are sandbox or disabled.
7. `WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE=False`.
8. `WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE=False`.
9. `WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE=False`.
10. `WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE=False`.
11. `WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE=False`.
12. Email backend is dummy/file/controlled mailbox.
13. Any banking/payment integrations are sandboxed or blocked at network level.
14. Locust credentials belong only to performance test users.
15. Test tenants are clearly named and disposable.

## Test Data And Tenant Matrix

Create three tenant sizes before Phase 2B execution:

| Tenant size | Purpose | Target fixture volume |
| --- | --- | --- |
| Small | Smoke, auth, permission, tenant isolation | 10 customers, 10 vendors, 100 invoices, 20 payments/receipts, 1 FY, 1 branch |
| Medium | Main controlled staging profile | 100 customers, 100 vendors, 5,000 invoices, 1,000 payments/receipts, GST data for reports, 2 branches |
| Large | Heavy report and pagination validation | 500 customers, 500 vendors, 50,000 invoices, 10,000 payments/receipts, AP/AR aging/open-item history, 3-5 branches |

Each tenant must include:

- Independent entity, subentity, financial year, GST registration, and subscription membership.
- Chart of accounts and static account mappings.
- Sales, purchase, payment, receipt, and journal voucher numbering series.
- Opening balances reconciled to ledger entries.
- Customer/vendor masters with GST and state data.
- Purchase and sales invoices across current and prior months.
- Payments, receipts, settlements, credit/debit notes, and open items.
- GST/GSTR report rows or deterministic imported GST datasets where applicable.
- Explicit tenant ownership assertions after seeding.

## Monitoring And Evidence Checklist

Capture all artifacts under `docs/qa/performance/evidence/phase2b/`.

Required during each controlled staging run:

- Locust HTML report.
- Locust stats CSV, failures CSV, exceptions CSV, and history CSV.
- Resource CSV from `perf/baseline/phase1d_resource_monitor.py`.
- Gunicorn service status before and after.
- Gunicorn worker PIDs, CPU, RSS, restart count.
- Nginx access/error logs for the window.
- PostgreSQL `pg_stat_activity` snapshots.
- PostgreSQL lock waits and deadlocks.
- PostgreSQL connection counts by state.
- Slow-query log or `pg_stat_statements` top queries.
- DB size, temp bytes, block reads/hits.
- Background job/timer logs.
- Before/after financial reconciliation snapshots.
- Tenant isolation checks.

Recommended PostgreSQL readiness:

- Enable `pg_stat_statements`.
- Enable slow-query logging for the test window, e.g. `log_min_duration_statement` at a staging-safe threshold.
- Confirm the telemetry user can read `pg_stat_activity`, `pg_locks`, and `pg_stat_database`.

## Locust Workload Profiles

Use the existing tags in `perf/locust/locustfile.py`.

Readiness smoke only:

```bash
locust -f perf/locust/locustfile.py --headless --users 1 --spawn-rate 1 --run-time 1m \
  --tags auth-health read-modern --csv docs/qa/performance/evidence/phase2b/smoke_1u \
  --html docs/qa/performance/evidence/phase2b/smoke_1u.html
```

Controlled read/report ladder for Phase 2B after Go:

```bash
locust -f perf/locust/locustfile.py --headless --users 1 --spawn-rate 1 --run-time 3m --tags read-modern,report-heavy
locust -f perf/locust/locustfile.py --headless --users 5 --spawn-rate 1 --run-time 5m --tags read-modern,report-heavy
locust -f perf/locust/locustfile.py --headless --users 10 --spawn-rate 2 --run-time 10m --tags read-modern,report-heavy
```

Write workflows remain gated:

- Keep `FINACC_ENABLE_WRITE_TESTS=false` until staging data reset and reconciliation are verified.
- Keep `FINACC_ENABLE_LIFECYCLE_TESTS=false` until disposable write tenants are loaded.
- Enable write/lifecycle profiles only after read profiles pass and before/after reconciliation scripts are ready.

## Acceptance Thresholds For Phase 2B Controlled Staging

Initial thresholds:

| Metric | Go threshold |
| --- | --- |
| HTTP error rate | 0% for smoke, <0.5% for controlled read/report runs |
| Auth failures | 0 unexpected failures |
| Tenant leakage | 0 tolerated |
| Financial reconciliation mismatch | 0 tolerated |
| Deadlocks | 0 tolerated in smoke/read; any write deadlock is stop-and-triage |
| Idle-in-transaction growth | No persistent growth across the run |
| PostgreSQL ungranted locks | No sustained lock waits; any repeated waits require triage |
| Gunicorn worker restarts | 0 unexpected restarts |
| App CPU | No sustained saturation across all workers without throughput gain |
| App RSS | No monotonic leak pattern across repeated runs |
| p95 latency | Report-heavy endpoints should stay within previously remediated local order of magnitude; regressions >2x require triage |

Stop conditions:

- Any production database/service detected.
- Any live GST filing/payment/email side effect detected.
- Any cross-tenant read/write leak.
- Any financial mismatch after workload.
- Persistent 5xx responses.
- Deadlock, runaway locks, or connection exhaustion.
- App worker restarts or memory growth suggesting instability.

## Reset Procedure Requirements

Before Phase 2B runs:

1. Snapshot or recreate the disposable staging DB.
2. Seed small/medium/large tenants from deterministic scripts.
3. Record tenant IDs, FY IDs, subentity IDs, and test users in a local-only `.env`.
4. Run reconciliation checks before load.
5. Run the load window.
6. Run reconciliation checks after load.
7. Archive evidence.
8. Reset DB before the next profile if writes were enabled.

## Current Blockers

P0:

- Staging environment has not been directly verified in this phase. No SSH/systemctl/PostgreSQL staging evidence was captured.
- No proof yet that staging DB credentials cannot reach production.
- No proof yet that live GST filing/email/banking/payment actions are blocked at staging runtime.
- Deterministic small/medium/large tenant seed commands are not yet documented as executable one-command reset procedures.

P1:

- Gunicorn is configured with 3 workers, but worker count has not been sized against staging CPU/RAM.
- PostgreSQL pooling/connection budget is not finalized for 10/25/50-user staging profiles.
- Redis/cache configuration for multi-worker staging is not confirmed.
- `pg_stat_statements` and slow-query logging are not confirmed enabled.
- Frontend production build and Nginx staging deployment were inspected from scripts only, not verified on the live staging host.

P2:

- Locust has rich read/report/write tags, but staging-specific profile wrapper commands should be checked into a repeatable script in the next phase.
- Browser-level frontend performance is not part of this API readiness gate.

## Go / No-Go Gate

**No-Go for controlled staging load execution today.**

The codebase has enough local certification and reusable tooling to proceed once the staging environment is verified, but Phase 2B.1 requires proof of staging isolation and observability before any multi-user staging load. Do not start Phase 2B load until the P0 blockers above are closed.

Recommended next step: verify the actual staging host and database configuration, create/reset disposable performance tenants, enable PostgreSQL telemetry, and run only the 1-user smoke profile after isolation checks pass.

---

# Phase 2B.2 - Staging Environment Safety And Readiness Gate Closure

Date: 2026-10-10  
Scope: safety/readiness gate only; no high-volume load executed; no destructive reset executed  
Verdict: **No-Go for Phase 2B.3 controlled staging load until live staging isolation evidence is captured**

## Phase 2B.2 Objective

Establish a demonstrably isolated, reproducible, and safe staging environment before any controlled staging load test. This pass added executable safety guards and documented the seed/reset procedure, but did not SSH into staging, provision infrastructure, run destructive commands, or run load.

## New Safety Artifacts

| Artifact | Purpose | Status |
| --- | --- | --- |
| `entity/management/commands/audit_performance_staging.py` | Redacted Django command that verifies staging DB allowlists, production-name guards, GST live flags, email safe sink, cache backend, storage target, and write-test gates | Added |
| `perf/staging/phase2b_readiness_gate.sh` | Repeatable readiness wrapper that captures staging audit, release audit, and telemetry snapshot under `docs/qa/performance/evidence/phase2b/` | Added |
| `perf/staging/phase2b_seed_reset.md` | Guarded seed/reset operating procedure for disposable staging tenants | Added |
| `docs/qa/performance/evidence/phase2b/staging_safety_audit_local_2026-10-10.json` | Local non-strict audit evidence proving the guard blocks an unallowlisted environment | Captured |

## Staging Isolation Evidence

The repository contains a staging deployment target and service configuration:

| Area | Evidence | Gate status |
| --- | --- | --- |
| Backend host | `deploy/ec2/deploy_backend_staging.sh` defaults `REMOTE_HOST=16.16.166.34`, `REMOTE_PROJECT_DIR=/home/ubuntu/Finacc`, branch `master` | **Blocked**: runtime host identity was not independently verified |
| Gunicorn | `deploy/ec2/gunicorn.service` runs `/home/ubuntu/Finacc/venv/bin/gunicorn FA.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120` with `/home/ubuntu/Finacc/.env` | **Verified from repo config**, **Blocked at runtime** until `systemctl cat/status` evidence is captured |
| Nginx | `deploy/ec2/nginx-staging.conf` proxies `/api/` to `127.0.0.1:8000` and serves Angular from `/var/www/finacc-staging` | **Verified from repo config**, **Blocked at runtime** until active Nginx config is captured |
| PostgreSQL endpoint | Runtime DB values come from the staging `.env`; no staging `.env` is stored in repo | **Blocked**: DB endpoint, DB name, DB user privileges, and production isolation are not proven |
| Redis/cache | Django supports Redis, but local/default observed cache is LocMem | **Blocked**: staging Redis endpoint and multi-worker cache behavior are not proven |
| Storage | Django supports local or S3 storage | **Blocked** if staging uses S3 until bucket/account name is proven staging/test/perf-only |
| Scheduled jobs | Deployment installs `finacc-platform-approval-expiry.timer` and `finacc-platform-access-expiry.timer` | **Verified from repo config**, **Blocked at runtime** until `systemctl list-timers` evidence is captured |

No proof has been captured that staging credentials cannot write to production databases, storage, queues, or financial services. That remains a P0 gate.

## Local Safety Audit Result

Command executed locally, non-strict:

```bash
venv/bin/python manage.py audit_performance_staging --json
```

Evidence saved:

```text
docs/qa/performance/evidence/phase2b/staging_safety_audit_local_2026-10-10.json
```

Result summary:

```text
ready=false
verified=10
blocked=3
```

Blocked locally:

- `DB_NAME_ALLOWLIST`: local DB name was not explicitly allowlisted as a performance staging DB.
- `DB_HOST_ALLOWLIST`: local DB host was not explicitly allowlisted as a performance staging host.
- `CACHE_MULTI_WORKER_READY`: local/default cache is LocMem, not Redis.

This is expected and desirable for a guard command: an unallowlisted local/developer environment must not be treated as staging-ready.

## External Integration Safety Matrix

| Integration | Repository/runtime setting reviewed | Safe condition | Phase 2B.2 status |
| --- | --- | --- | --- |
| Whitebooks GST/e-invoice/e-waybill | `WHITEBOOKS_BASE_URL`, `WHITEBOOKS_SANDBOX_MODE`, live GSTR flags | Sandbox URL, sandbox mode true, all live save/file/offset flags false | **Verified locally**, **Blocked for live staging** until runtime audit is captured |
| MasterGST | `MASTERGST_ENV`, `MASTERGST_BASE_URL` | `SANDBOX`, `TEST`, or disabled | **Verified locally**, **Blocked for live staging** until runtime audit is captured |
| Email | `EMAIL_BACKEND` | `locmem`, `console`, `dummy`, or `filebased` during load windows | **Verified locally**, **Blocked for live staging** until runtime audit is captured |
| SMS | No direct SMS config found in reviewed settings/deploy evidence | No side-effecting provider configured | **Not Applicable based on repo scan**, verify staging env for hidden provider vars |
| Payment gateway/banking APIs | Bank reconciliation/payment modules exist; no live provider config proven safe | Network blocked or sandbox-only; no production banking credentials | **Blocked** |
| Webhooks | No staging webhook dispatch matrix found | Disabled or safe sink during load | **Blocked** until runtime env and job config are audited |
| Background jobs | systemd timers for platform approval/access expiry | Listed, understood, monitored, and non-financial during load window | **Blocked at runtime** until timer/service logs are captured |
| File storage | `FILE_STORAGE_BACKEND`, optional S3 settings | Local storage or staging/test/perf S3 bucket only | **Verified locally as local**, **Blocked for live staging** if S3 is used |

## Deterministic Tenant Seed/Reset Documentation

Seed/reset documentation was added at:

```text
perf/staging/phase2b_seed_reset.md
```

Current safe procedure:

1. Set explicit DB allowlists:

   ```bash
   export FINACC_PERF_ALLOWED_DB_NAMES=<staging_perf_db_name>
   export FINACC_PERF_ALLOWED_DB_HOSTS=<staging_postgres_host>
   export FINACC_ENABLE_WRITE_TESTS=false
   export FINACC_ENABLE_LIFECYCLE_TESTS=false
   ```

2. Run the readiness gate:

   ```bash
   bash perf/staging/phase2b_readiness_gate.sh
   ```

3. Dry-run scoped transactional reset only after the gate passes:

   ```bash
   python manage.py reset_transactional_data \
     --entity <ENTITY_ID> \
     --entityfinid <ENTITY_FIN_ID> \
     --subentity <SUBENTITY_ID> \
     --dry-run
   ```

4. Use existing idempotent launch fixture seed for master/reference bootstrapping:

   ```bash
   python manage.py seed_launch_validation_data \
     --entity-id <ENTITY_ID> \
     --actor-email <PERF_OPERATOR_EMAIL> \
     --json
   ```

Remaining fixture blocker: the existing seed command does not yet create the full small/medium/large Phase 2B accounting volume matrix. A dedicated deterministic performance fixture generator is still required for realistic invoice/payment/report volumes.

## Readiness Gate Checklist

| Gate | Required evidence | Status |
| --- | --- | --- |
| Staging app host identity | SSH host fingerprint, instance ID/hostname, CPU/RAM/disk snapshot | **Blocked** |
| Active Gunicorn config | `systemctl cat finacc-gunicorn`, status, worker PIDs | **Blocked** |
| Active Nginx config | `nginx -T` redacted relevant server block, access/error log paths | **Blocked** |
| Staging DB identity | DB host, DB name, current database, non-production account identifier, read-only proof against prod | **Blocked** |
| DB least privilege | DB user grants limited to staging DB/schema | **Blocked** |
| Redis/cache | Redis endpoint, DB index/key prefix, cache backend audit | **Blocked** |
| External financial services | GST/payment/banking/email/webhook safe sinks or sandbox proof | **Blocked** |
| Scheduled jobs | `systemctl list-timers` and job logs for load window | **Blocked** |
| Monitoring | telemetry CSV, pg activity/locks, worker CPU/RSS, Nginx/Gunicorn logs | **Tooling Ready**, runtime evidence blocked |
| Seed/reset | dry-run reset, deterministic seed output, before/after reconciliation | **Partially Ready**, full volume generator blocked |
| Locust write gates | write/lifecycle env flags disabled by default | **Verified locally** |
| Production protection | audit command refuses unallowlisted DB name/host and production-like identifiers | **Verified locally** |

## Phase 2B.3 Go / No-Go

**No-Go.**

Phase 2B.2 improved the safety tooling and documented the guarded seed/reset path, but it did not close the live staging evidence gap. Controlled staging load may begin only after:

- `audit_performance_staging --strict` passes on the actual staging host with explicit DB name/host allowlists.
- The readiness wrapper captures release audit and telemetry evidence on staging.
- External financial side effects are proven sandboxed, disabled, or routed to safe sinks.
- Disposable small/medium/large tenant fixture seeding is executable and reconciled.
- Reset commands are reviewed in dry-run mode and explicitly authorized for the verified staging database.

No high-volume load, destructive reset, production data access, or paid provisioning was performed in Phase 2B.2.
