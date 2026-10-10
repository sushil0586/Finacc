# Finacc Phase 2B.3B - Deterministic Multi-Tenant Performance Fixture Readiness

Date: 2026-10-10  
Scope: deterministic fixture generator and tiny disposable validation only  
Verdict: **Ready for controlled larger fixture dry-runs; not yet approved for full medium/large generation**

## Objective

Prepare a reusable, idempotent, safety-gated fixture generator for local production-like performance testing. The generator must seed isolated tenants with accounting-shaped sales, purchase, AP/AR open item, settlement, numbering, GST, and posting data without touching production or external services.

## Safety Verification

Docker services were running:

```text
postgres healthy on local port 15432
redis healthy on local port 16379
web healthy on local port 18000
nginx running on local port 18080
```

Database identity was verified directly in PostgreSQL:

```text
current_database = finacc_perf_local
current_user     = finacc_perf
```

Strict performance safety audit passed before writes:

```text
performance_staging_ready=True verified=13 blocked=0 not_applicable=0
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b_safety_audit_2026-10-10.json
```

## Generator Added

New command:

```text
entity/management/commands/seed_performance_fixtures.py
```

Capabilities:

- Fails closed through `audit_performance_staging --strict`.
- Requires explicit DB name/host allowlists.
- Creates three independent tenants per profile: S/M/L fixture tenants.
- Creates independent entity, subentity, FY, GST registration, geography, users, ledgers, accounts, voucher/document series, products/UOMs.
- Seeds posted sales invoices, purchase invoices, AP open items, AR open items, settlements for a configurable ratio, tax summaries, and balanced journal entries.
- Uses deterministic random seed and batch ranges.
- Supports resumable/idempotent execution by counting existing generated rows and inserting only missing rows.
- Supports dry-run and fixture-scoped reset dry-run.
- Prevents production execution through the staging safety audit and production-name guards.

Important design note: the generator creates posted performance fixture documents directly through models with balanced postings and open items. It does not call confirm/post APIs for every invoice. This keeps high-volume fixture generation feasible while preserving list/report/open-item semantics. API write-concurrency correctness remains covered by Phase 2A.

## Target Profiles

Default target volumes per tenant:

| Profile | Sales invoices | Purchase invoices | Automatic execution status |
| --- | ---:| ---:| --- |
| `tiny` | 4 | 3 | Executed |
| `small` | 1,000 | 500 | Not executed |
| `medium` | 10,000 | 5,000 | Not executed |
| `large` | 50,000 | 25,000 | Not executed |

The command supports overrides:

```bash
python manage.py seed_performance_fixtures \
  --profile small \
  --sales 1000 \
  --purchase 500 \
  --batch-size 500 \
  --seed 20261010 \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

## Tiny Fixture Validation

Executed:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile tiny \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b_tiny_seed_2026-10-10.json
```

Measured result:

```text
elapsed_seconds = 0.723
database_before = 65,297,431 bytes
database_after  = 69,729,303 bytes
growth          = 4,431,872 bytes
```

Rows generated:

| Tenant | Entity ID | Sales inserted | Purchase inserted | Validation |
| --- | ---:| ---:| ---:| --- |
| `P2B3B-TINY-S` | 1 | 4 | 3 | Passed |
| `P2B3B-TINY-M` | 2 | 4 | 3 | Passed |
| `P2B3B-TINY-L` | 3 | 4 | 3 | Passed |

Per-tenant validation:

```text
sales_count = 4
purchase_count = 3
AR open total = 1,770.00
AP open total = 1,180.00
journal_debit = 4,130.00
journal_credit = 4,130.00
balanced = true
duplicate_sales_doc_numbers = 0
duplicate_purchase_doc_numbers = 0
```

## Idempotency / Resume Validation

The same tiny command was run again after the initial seed.

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b_tiny_idempotency_2026-10-10.json
```

Result:

```text
sales_inserted = 0
purchase_inserted = 0
database size unchanged
financial validation still passed
```

An idempotency bug was found and fixed during this phase: reruns initially reused existing ledgers but attempted to create duplicate `financial.account` records for the same one-to-one ledger. The generator now reuses `ledger.account_profile` when present.

## Reset Safety Validation

Reset dry-run only:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --reset-fixture \
  --dry-run \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Observed scope:

```text
entities = 3
sales_headers = 12
purchase_headers = 9
```

No destructive reset was executed.

## Resource Snapshot

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b_docker_stats_2026-10-10.txt
```

Snapshot after validation:

```text
finacc-nginx-1      0.00%     8.531MiB / 7.748GiB
finacc-postgres-1   0.00%     92.1MiB / 7.748GiB
finacc-redis-1      0.42%     10.09MiB / 7.748GiB
finacc-web-1        200.43%   425.1MiB / 7.748GiB
```

Local limitation: Docker stats are momentary and include container startup/rebuild effects. They are useful for smoke evidence only, not capacity certification.

## Sizing Estimate

Tiny generation inserted 21 invoices total plus related open items, settlements, tax summaries, journal entries, tenants, masters, and indexes. Initial DB growth was about 4.43 MB, but this includes fixed master-data overhead for the first tenants.

Do not extrapolate linearly from the tiny fixture as production capacity. For planning only:

- Small profile creates 4,500 invoices total across three tenants.
- Medium profile creates 45,000 invoices total across three tenants.
- Large profile creates 225,000 invoices total across three tenants.

Recommended next validation ladder:

```bash
# Small dry-run first
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile small \
  --dry-run \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres

# Then a capped small smoke, not full profile
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile small \
  --sales 100 \
  --purchase 50 \
  --batch-size 100 \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

## Safe Execution Commands

Audit:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py audit_performance_staging \
  --strict \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Tiny seed:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile tiny \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Reset preview:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --reset-fixture \
  --dry-run \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Actual fixture reset, only after approval:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --reset-fixture \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

## Remaining Risks

P1:

- The generator seeds accounting-shaped posted documents directly through models, not full create/confirm/post APIs. This is intentional for volume generation, but API lifecycle correctness must continue to rely on Phase 2A tests.
- Payment vouchers/receipt vouchers are represented as posted AP/AR settlements in the tiny fixture; full payment/receipt voucher volume can be added after report workloads confirm the current fixture shape is sufficient.
- GST data is invoice/tax-summary level. External GST filing/e-invoice/e-waybill artifacts are intentionally not generated in this local phase.

P2:

- Large profile disk/time estimate should be measured through an intermediate capped run before full generation.
- Background timers are not represented in this local fixture validation.

## Readiness Verdict

**Ready for larger fixture dry-runs and capped small-volume generation.**

Do not generate full medium or large profiles yet. Recommended next step is a capped `small --sales 100 --purchase 50` run with telemetry, then validate report/API behavior and database growth before approving the full small profile.

---

# Phase 2B.3B.1 - Controlled Performance Fixture Volume Validation

Date: 2026-10-10  
Scope: capped small-volume generation only; no destructive reset; no medium/large generation; no Locust load  
Verdict: **Pass for capped small-volume fixture generation**

## CLI And Scope Verification

Verified command syntax:

```text
python manage.py seed_performance_fixtures
  --profile {tiny,small,medium,large}
  --sales SALES
  --purchase PURCHASE
  --batch-size BATCH_SIZE
  --seed SEED
  --payment-ratio PAYMENT_RATIO
  --json
  --dry-run
  --reset-fixture
  --allow-db-name ALLOW_DB_NAME
  --allow-db-host ALLOW_DB_HOST
```

`--sales` and `--purchase` are **per tenant** overrides. The generator creates three tenants per profile. Therefore this capped run:

```text
--profile small --sales 100 --purchase 50
```

means:

```text
3 tenants
300 sales invoices total
150 purchase invoices total
450 invoices total
```

## Safety And Identity

Docker DB identity:

```text
current_database = finacc_perf_local
current_user = finacc_perf
```

Strict safety audit:

```text
ready = true
verified_count = 13
blocked_count = 0
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b1_safety_audit_2026-10-10.json
docs/qa/performance/evidence/phase2b/phase2b3b1_small_capped_dry_run_2026-10-10.json
```

Dry-run result:

```text
P2B3B-SMALL-S: sales=100, purchase=50
P2B3B-SMALL-M: sales=100, purchase=50
P2B3B-SMALL-L: sales=100, purchase=50
No rows written during dry-run.
```

## Generator Fixes During Validation

Two idempotent fixture-identity defects were discovered before successful capped generation:

- Geography lookup used display name in `State.get_or_create`, while the real unique identity is `country + statecode`.
- Entity GSTIN generation reused values across profiles for the same S/M/L tenant suffix.

Both were fixed in the generator without changing accounting business rules. After the fixes, the capped seed completed and idempotency passed.

## Capped Small Seed Result

Executed:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile small \
  --sales 100 \
  --purchase 50 \
  --batch-size 100 \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b1_small_capped_seed_2026-10-10.json
```

Measured result:

```text
elapsed_seconds = 3.470
database_before = 69,729,303 bytes
database_after  = 72,997,911 bytes
growth          = 3,268,608 bytes
```

Inserted rows:

| Tenant | Entity ID | Sales inserted | Purchase inserted | Validation |
| --- | ---:| ---:| ---:| --- |
| `P2B3B-SMALL-S` | 5 | 100 | 50 | Passed |
| `P2B3B-SMALL-M` | 6 | 100 | 50 | Passed |
| `P2B3B-SMALL-L` | 7 | 100 | 50 | Passed |

Per-tenant validation:

```text
sales_count = 100
purchase_count = 50
sales_total = 59,000.00
purchase_total = 29,500.00
AR open total = 47,200.00
AP open total = 23,600.00
journal_debit = 88,500.00
journal_credit = 88,500.00
balanced = true
duplicate_sales_doc_numbers = 0
duplicate_purchase_doc_numbers = 0
```

SQL reconciliation evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b1_sql_reconciliation_2026-10-10.txt
```

## Idempotency Validation

The same capped small command was run again.

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b1_small_capped_idempotency_2026-10-10.json
```

Result:

```text
sales_inserted = 0
purchase_inserted = 0
database_before = database_after = 72,997,911 bytes
financial validation remained balanced
duplicate doc numbers remained 0
```

## Resource And Database Observations

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b1_docker_stats_before_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b1_docker_stats_after_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b1_pg_activity_after_2026-10-10.txt
```

Post-run Docker stats snapshot:

```text
finacc-nginx-1      0.00%     8.531MiB / 7.748GiB
finacc-postgres-1   1.05%     95.83MiB / 7.748GiB
finacc-redis-1      0.69%     10.08MiB / 7.748GiB
finacc-web-1        100.62%   357.7MiB / 7.748GiB
```

Post-run PostgreSQL activity:

```text
total_connections = 1
active = 1
idle_in_tx = 0
waiting = 0
ungranted_locks = 0
```

## Regression Checks

Completed:

```text
python manage.py check
System check identified no issues.
```

Completed fixture-level financial regression:

- tenant ownership isolated by entity IDs 5, 6, and 7;
- sales/purchase counts matched target counts per tenant;
- invoice numbering unique inside tenant/FY/subentity/doc-code scope;
- journal debit/credit equality matched per tenant;
- AP and AR outstanding totals matched expected settlement ratio;
- tax totals matched `500.00 taxable + 90.00 IGST = 590.00 gross`.

Attempted:

```text
perf.tests_phase2a_write_concurrency.PurchaseInvoicePhase2AConcurrencyTests.test_journal_voucher_concurrent_confirm_and_post_at_2_5_10_workers
```

The container spent several minutes in test database setup/seed work and was manually interrupted to keep this phase bounded. No pass is claimed for that test in Phase 2B.3B.1. Phase 2A remains the source of API write-concurrency certification evidence.

## Bottlenecks / Notes

- Capped generation itself was fast: 450 invoices in 3.47 seconds.
- The main bottleneck discovered was fixture identity/idempotency setup, now fixed for geography and entity GSTIN.
- Direct model fixture generation remains appropriate for read/report performance volumes; it is not a replacement for API lifecycle tests.

## Phase 2B.3B.1 Verdict

**Pass.**

The local Docker performance environment safely supports expanded small-fixture generation beyond the tiny smoke. The next safe step is a full small dry-run, followed by full small generation only after explicit approval and telemetry capture. Do not generate medium or large datasets yet.

---

# Phase 2B.3B.2 - Full Small Multi-Tenant Fixture Validation

Date: 2026-10-10  
Scope: full small fixture only; no destructive reset; no Locust load; no medium/large generation  
Verdict: **Pass**

## Target And CLI Scope

Verified CLI:

```text
--profile small
--sales SALES       # per tenant override
--purchase PURCHASE # per tenant override
--batch-size BATCH_SIZE
--dry-run
--reset-fixture
--allow-db-name
--allow-db-host
```

Full small target:

```text
3 tenants
1,000 sales invoices per tenant
500 purchase invoices per tenant
4,500 invoices total
```

The database already contained the capped Phase 2B.3B.1 fixture:

```text
100 sales invoices per tenant
50 purchase invoices per tenant
```

Therefore the full-small run topped up each tenant by:

```text
900 sales invoices
450 purchase invoices
```

## Safety And Resource Gates

Docker services were healthy before execution. PostgreSQL identity:

```text
current_database = finacc_perf_local
current_user = finacc_perf
```

Strict safety audit:

```text
ready = true
verified_count = 13
blocked_count = 0
```

Pre-seed DB and connection state:

```text
db_size_bytes = 73,120,791
connections = 1
idle_in_tx = 0
```

Local disk before:

```text
Filesystem /dev/disk3s5
Size 460Gi
Used 273Gi
Available 153Gi
Capacity 65%
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_safety_audit_2026-10-10.json
docs/qa/performance/evidence/phase2b/phase2b3b2_full_small_dry_run_2026-10-10.json
docs/qa/performance/evidence/phase2b/phase2b3b2_pre_counts_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b2_docker_stats_before_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b2_disk_before_2026-10-10.txt
```

Dry-run confirmed the target without writes:

```text
P2B3B-SMALL-S: sales=1000, purchase=500
P2B3B-SMALL-M: sales=1000, purchase=500
P2B3B-SMALL-L: sales=1000, purchase=500
```

## Full Small Seed Result

Executed:

```bash
docker compose -f docker-compose.perf.yml exec -T web \
  python manage.py seed_performance_fixtures \
  --profile small \
  --batch-size 500 \
  --json \
  --allow-db-name finacc_perf_local \
  --allow-db-host postgres
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_full_small_seed_2026-10-10.json
docs/qa/performance/evidence/phase2b/phase2b3b2_full_small_seed_window_2026-10-10.txt
```

Measured result:

```text
elapsed_seconds = 28.770
database_before = 73,120,791 bytes
database_after  = 102,054,935 bytes
growth          = 28,934,144 bytes
```

Inserted rows:

| Tenant | Entity ID | Sales inserted | Purchase inserted | Final sales | Final purchase |
| --- | ---:| ---:| ---:| ---:| ---:|
| `P2B3B-SMALL-S` | 5 | 900 | 450 | 1,000 | 500 |
| `P2B3B-SMALL-M` | 6 | 900 | 450 | 1,000 | 500 |
| `P2B3B-SMALL-L` | 7 | 900 | 450 | 1,000 | 500 |

Post-seed resource snapshot:

```text
finacc-nginx-1      0.00%     8.531MiB / 7.748GiB
finacc-postgres-1   26.99%    198.4MiB / 7.748GiB
finacc-redis-1      0.34%     10.39MiB / 7.748GiB
finacc-web-1        196.27%   622.2MiB / 7.748GiB
```

Post-seed PostgreSQL:

```text
total_connections = 1
active = 1
idle_in_tx = 0
waiting = 0
ungranted_locks = 0
db_size_bytes = 102,276,119
```

The slight DB-size difference between command output and post-run snapshot is expected because PostgreSQL relation/index metadata can settle after transactions complete.

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_docker_stats_after_seed_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b2_pg_activity_after_seed_2026-10-10.txt
```

## Financial Reconciliation

SQL reconciliation evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_sql_reconciliation_2026-10-10.txt
```

Per tenant:

```text
sales_count = 1,000
purchase_count = 500
sales_total = 590,000.00
purchase_total = 295,000.00
AR open total = 472,000.00
AP open total = 236,000.00
journal_debit = 885,000.00
journal_credit = 885,000.00
balanced = true
duplicate sales doc numbers = 0
duplicate purchase doc numbers = 0
```

Validation coverage:

- Tenant ownership isolated by entity IDs 5, 6, and 7.
- Document numbering unique per tenant/FY/subentity/doc-code.
- AP/AR outstanding matched the deterministic 20% settlement ratio.
- Journal debit and credit matched per tenant.
- Tax math matched `500.00 taxable + 90.00 IGST = 590.00 gross`.
- Purchase totals matched `500 * 590.00 = 295,000.00` per tenant.
- Sales totals matched `1,000 * 590.00 = 590,000.00` per tenant.

## Idempotency

The identical full-small command was rerun.

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_full_small_idempotency_2026-10-10.json
```

Result:

```text
sales_inserted = 0
purchase_inserted = 0
database_before = database_after = 102,276,119 bytes
financial validation remained balanced
duplicate doc numbers remained 0
```

## Regression Checks

Completed:

```text
python manage.py check
System check identified no issues.
```

Completed bounded regression:

```text
python manage.py test entity.tests.test_release_environment_audit --keepdb
Ran 5 tests in 0.023s
OK
```

Evidence:

```text
docs/qa/performance/evidence/phase2b/phase2b3b2_manage_check_2026-10-10.txt
docs/qa/performance/evidence/phase2b/phase2b3b2_bounded_regression_2026-10-10.txt
```

Earlier Phase 2B.3B.1 showed the heavier Phase 2A concurrency test path spends minutes in container test database setup. For this fixture-validation phase, bounded regression was used instead of silently claiming that heavier coverage passed. Phase 2A remains the source of write-concurrency certification evidence.

## Fixture Realism Statement

These fixtures are synthetic, deterministic, posted accounting fixtures. They are intended to exercise:

- report and lookup volumes;
- tenant scoping;
- document numbering;
- AP/AR open item totals;
- settlement totals;
- GST/tax summaries;
- journal debit/credit equality;
- invoice list and aging/open-item query paths.

They do **not** prove every real user workflow step for invoice create/confirm/post, payment voucher posting, or receipt voucher posting. Those behaviors are covered by API and concurrency suites from earlier phases and must remain separate from bulk fixture generation.

## Phase 2B.3B.2 Verdict

**Pass.**

The Docker performance environment supports the full small multi-tenant fixture volume with clean safety gates, successful generation, successful idempotency, clean PostgreSQL lock/connection state, and balanced financial reconciliation.

Recommended next step: use this full-small dataset for controlled read/report smoke and API baseline checks. Do not generate medium or large datasets until report/API behavior on the full-small fixture is measured.
