# Phase 2B Staging Seed And Reset Procedure

This procedure is intentionally guarded. Do not run destructive reset or write-load setup until the staging database identity is positively verified.

## Required Environment

Set these variables only on the staging/performance operator shell:

```bash
export FINACC_PERF_ALLOWED_DB_NAMES=finacc_staging_perf
export FINACC_PERF_ALLOWED_DB_HOSTS=staging-postgres.internal
export FINACC_ENABLE_WRITE_TESTS=false
export FINACC_ENABLE_LIFECYCLE_TESTS=false
```

Use the real staging DB name and host values. Do not put secrets in this file.

## Safety Gate

Run the gate before any reset, seed, or Locust profile:

```bash
bash perf/staging/phase2b_readiness_gate.sh
```

The gate must pass `audit_performance_staging --strict`. It refuses readiness when:

- the current DB name or DB host is not explicitly allowlisted;
- the DB name or host looks production/live;
- GST live mutation flags are enabled;
- email is configured for real SMTP delivery;
- write/lifecycle Locust flags are enabled before the read-only gate;
- Redis is not configured for multi-worker cache behavior;
- S3 storage is not local or staging/test/perf named.

## Reset Pattern

The existing transactional reset command is scoped by entity, financial year, and subentity:

```bash
python manage.py reset_transactional_data \
  --entity <ENTITY_ID> \
  --entityfinid <ENTITY_FIN_ID> \
  --subentity <SUBENTITY_ID> \
  --dry-run
```

Only after the safety gate passes and the dry run has been reviewed may the same command be run without `--dry-run`.

## Master Data Seed Pattern

The existing launch validation seed command is idempotent and can bootstrap master/reference data:

```bash
python manage.py seed_launch_validation_data \
  --entity-id <ENTITY_ID> \
  --actor-email <PERF_OPERATOR_EMAIL> \
  --json
```

Current limitation: this command does not yet create the full Phase 2B small/medium/large accounting volume matrix. A dedicated deterministic performance fixture generator is still required before controlled staging load can be certified.

## Required Tenant Matrix

Before Phase 2B.3, create and record:

| Tenant | Purpose | Minimum volume |
| --- | --- | --- |
| Small | smoke and auth validation | 100 invoices, 20 payments/receipts |
| Medium | primary controlled load | 5,000 invoices, 1,000 payments/receipts |
| Large | heavy report validation | 50,000 invoices, 10,000 payments/receipts |

Each tenant must have independent users, company/entity, subentity, financial year, ledgers, voucher series, customers, vendors, GST data, opening balances, invoices, payments, receipts, credit/debit notes, and reconciliation snapshots.
