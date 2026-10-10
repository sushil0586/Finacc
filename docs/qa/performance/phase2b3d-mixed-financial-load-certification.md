# Finacc Phase 2B.3D - Controlled Docker Multi-Tenant Mixed Read/Write Financial Load Certification

Date: 2026-10-10  
Environment: local Docker performance stack  
Database verified: `finacc_perf_local`  
Requested ceiling: maximum 10 total virtual users and 5 active writers  

## Verdict

**Conditional / Blocked for persistent Docker mixed read/write load.**

The financial write-concurrency contracts were revalidated successfully in the existing disposable Phase 2A harness, but the persistent Docker mixed read/write Locust run was **not executed** because the required separately scoped Docker write-test dataset and HTTP-authenticated write users are not yet provisioned.

This is an intentional safety stop. The certified 4,500-invoice read/report fixtures were not modified.

## What Was Verified

Safety and environment checks passed:

- Docker services were healthy.
- Database identity was verified as `finacc_perf_local`.
- Strict performance safety audit passed.
- `pg_stat_statements` remains enabled.
- The certified read/report fixture financial snapshot was captured before and after the regression run and remained unchanged.

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3d_safety_audit_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3d_db_identity_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3d_read_fixture_financial_before_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3d_read_fixture_financial_after_regression_2026-10-10.json`
- `docs/qa/performance/evidence/phase2b/phase2b3d_docker_stats_before_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3d_docker_stats_after_regression_2026-10-10.txt`
- `docs/qa/performance/evidence/phase2b/phase2b3d_pg_activity_after_regression_2026-10-10.txt`

## Financial Regression Result

The existing Phase 2A financial write-concurrency regression suite was executed inside the Docker web container against the disposable Django test database `test_finacc_perf_local` using `--keepdb`.

Command class:

- `perf.tests_phase2a_write_concurrency`

Result:

- 10 tests executed.
- 10 passed.
- Runtime: 116.075 seconds.
- Django system check passed.

Covered scenarios:

- Sales invoice concurrent confirm at 2/5/10 workers.
- Sales invoice duplicate/concurrent post idempotency for the same invoice.
- Purchase invoice concurrent confirm at 2/5/10 workers.
- Purchase invoice duplicate/concurrent post idempotency for the same invoice.
- AP settlement concurrent allocations against the same invoice at 2/5/10 workers.
- AP settlement concurrent payments against different invoices for the same vendor at 2/5/10 workers.
- Payment voucher concurrent numbering at 2/5/10 workers.
- Payment voucher concurrent confirm/post closing different invoices at 2/5/10 workers.
- Journal voucher concurrent confirm/post at 2/5/10 workers.
- Cross-tenant sales, purchase, and payment writes at 2/5/10 workers, including unauthorized cross-tenant misuse rejection.

Evidence:

- `docs/qa/performance/evidence/phase2b/phase2b3d_phase2a_concurrency_regression_keepdb_2026-10-10.log`
- `docs/qa/performance/evidence/phase2b/phase2b3d_phase2a_concurrency_regression_keepdb_exit_2026-10-10.txt`

## Certified Read Fixture Preservation

The certified 4,500-invoice read/report baseline fixtures were unchanged after the write-concurrency regression:

| Entity | Sales Invoices | Purchase Invoices | AR Open | AP Open |
|---:|---:|---:|---:|---:|
| 5 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 6 | 1,000 | 500 | 472,000.00 | 236,000.00 |
| 7 | 1,000 | 500 | 472,000.00 | 236,000.00 |

## Why Persistent Mixed Load Was Not Run

Phase 2B.3D requires a separately scoped, disposable write-test dataset with independent:

- Tenants / entities.
- Authorized users.
- RBAC write permissions.
- Subscription memberships.
- Financial years.
- Numbering series.
- Ledgers and static account mappings.
- Customers/vendors.
- Opening balances and open items.

The current Docker performance environment has certified read/report users and read/report fixtures. It does not yet have a verified persistent write-load tenant set that can be safely mutated without changing the Phase 2B.3C certified read/report baseline.

Running mixed write load against entities 5/6/7 would alter the certified read fixture counts and balances. Granting broad permissions or hand-writing records ad hoc would weaken the certification evidence. Therefore the persistent HTTP mixed-load run was stopped before any write traffic.

## Blocked Items

| Gate | Status | Detail |
|---|---|---|
| Docker DB identity | Verified | `finacc_perf_local` |
| Strict safety audit | Verified | Passed |
| Existing read fixture preservation | Verified | Unchanged before/after |
| Disposable write-concurrency contracts | Verified | Phase 2A regression passed |
| Persistent Docker write-test dataset | Blocked | Not provisioned yet |
| HTTP authenticated write users | Blocked | Current perf users are read/report users |
| Nginx -> Gunicorn mixed read/write Locust run | Blocked | Correctly not run without safe write dataset |
| 2-writer and 5-writer mixed load | Blocked | Requires the above gates first |

## Required Next Step

Before rerunning Phase 2B.3D, add a safety-gated, idempotent Docker write-fixture provisioning command that:

1. Refuses to run unless `audit_performance_staging --strict` passes for `finacc_perf_local`.
2. Creates new write-only performance tenants, separate from entities 5/6/7.
3. Creates local-only write users from environment-supplied credentials.
4. Uses real application provisioning services for subscriptions, memberships, and RBAC.
5. Seeds ledgers, static account mappings, voucher series, customers, vendors, payment modes, and opening/open-item records.
6. Produces before/after reconciliation snapshots.
7. Supports cleanup only with a separate explicit safety gate.

After that, implement a mixed Locust workload with:

- 60% existing read/report tasks.
- 40% write workflows against only the new write tenants.
- 2 active writers first, then 5 active writers only if 2-writer reconciliation passes.
- Maximum 10 total virtual users.
- Per-profile financial reconciliation and `pg_stat_statements` capture.

## Final Status

Phase 2B.3D is **not failed for financial correctness**. The available write-concurrency evidence passed.

The phase is **Conditional / Blocked** because the persistent Docker HTTP mixed-load prerequisites are incomplete, and executing write traffic against the certified read fixtures would violate the phase safety requirements.

