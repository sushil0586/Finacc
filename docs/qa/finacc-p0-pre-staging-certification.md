# Finacc P0 Pre-Staging Certification

Date: 2026-10-12  
Environment verified: isolated Docker performance stack  
Database: `finacc_perf_local` on Docker PostgreSQL  
Verdict: **CONDITIONAL READY for AWS staging execution**

This certification closes the four P0 gates identified in the master launch coverage audit before AWS production-like staging execution. It does not approve production launch.

## Evidence

| Evidence | Result |
|---|---:|
| Docker service health | Captured in `docs/qa/evidence/p0-pre-staging/docker_ps_2026-10-12.txt` |
| Database identity | `finacc_perf_local`, user `finacc_perf`, size `1635 MB` |
| Strict safety audit | PASS: `ready=true`, `verified_count=13`, `blocked_count=0` |
| Django system check | PASS: no issues |
| Migration consistency | PASS: no changes detected |
| Targeted financial/GST regressions | PASS: 425 tests in 440.882s, `OK` |

## P0 Gate Results

| Gate | Status | Evidence |
|---|---|---|
| P0-1 financial-statement truth pack | **PASS** | `reports.tests_accounting_truth_matrix` verifies independent service and trading datasets across Trial Balance, Balance Sheet, Trading Account, P&L, General Ledger/Ledger Summary, Cash/Bank Book via account movement, Daybook, receivables/payables, GST and inventory valuation. |
| P0-2 GSTR9 launch disposition | **PASS WITH SCOPE** | `reports.gstr9.tests.test_gstr9_scaffold_api` validates summary, table coverage, freeze/history, JSON/CSV/XLSX export contracts, RBAC restrictions, simulated filing and manual-provider flow. Recommendation: certify GSTR9 report/export/freeze/manual/simulated workflows for staging; keep live automated submission excluded unless separately provider-certified. |
| P0-3 external GST/provider route safety | **PASS FOR LOCAL DOCKER; AWS RERUN REQUIRED** | Strict audit verifies WhiteBooks sandbox routing, all live mutation flags disabled, MasterGST sandbox, local safe email sink, local storage, Redis cache, and write/lifecycle load gates off. AWS staging deployment was reported complete by the user, but this run did not access AWS infrastructure; rerun the same strict audit in AWS before staging tests. |
| P0-4 export parity for launch-critical reports | **PASS / CONDITIONAL UI SIGNOFF** | Backend export contracts are covered for financial reports, Trial Balance exports, GSTR9 JSON/CSV/XLSX, and GST preview exports. Browser-level PDF/print layout signoff remains P1 because it is environment-sensitive and not required to block AWS staging execution. |

## Truth-Pack Expected Values

### Dataset A: service entity

| Area | Expected result |
|---|---|
| Daybook | 7 active transactions; debit `41040.00`; credit `41040.00`; vouchers `A2-SALE` through `A8-TRANSFER`; draft/reversed entries excluded from active books. |
| Trial Balance | closing debit `111800.00`; closing credit `111800.00`; Main Bank `102080.00`; Cash `5000.00`; customer and vendor closed to `0.00`. |
| Ledger Summary | balance debit `111800.00`; balance credit `111800.00`; Input CGST `360.00`; Output CGST `-900.00`. |
| P&L | income `10000.00`; expense `4000.00`; net profit `6000.00`. |
| Balance Sheet | assets `107800.00`; liabilities/equity `107800.00`; net profit carried to equity `6000.00`; difference `0.00`. |
| Receivables/Payables | customer open item `11800.00` settled to `0.00`; vendor open item `4720.00` settled to `0.00`. |
| GST | outward taxable `10000.00`; output tax `1800.00`; inward taxable `4000.00`; input tax `720.00`; net liability `1080.00`. |

### Dataset B: trading entity

| Area | Expected result |
|---|---|
| Daybook | 7 active transactions; debit `67280.00`; credit `67280.00`. |
| Trial Balance | closing debit `119900.00`; closing credit `119900.00`; bank `103756.00`; customer/vendor `0.00`; Input CGST `972.00`; Output CGST `-1350.00`. |
| Ledger Summary | purchases `12000.00`; purchase returns `-1200.00`; sales `-16000.00`; sales returns `1000.00`. |
| Inventory/Trading | FIFO closing quantity `15.00`; closing value `1800.00`; trading gross profit `4800.00`. |
| P&L and Balance Sheet | net profit `4800.00`; assets `107500.00`; liabilities/equity `107500.00`; difference `0.00`. |
| GST | input tax `1944.00`; output tax `2700.00`; net liability `756.00`; purchase taxable `10800.00`; outward taxable `15000.00`. |

## External Integration Safety

The strict safety audit verified:

- `DEBUG=False`.
- Database name and host are allowlisted and not production-like.
- PostgreSQL is used.
- WhiteBooks GST uses sandbox routing.
- Live WhiteBooks flags are disabled: GSTR1 save/file and GSTR3B save/offset/file.
- MasterGST environment is `SANDBOX`.
- Email backend is a non-delivery safe sink.
- Storage target is local.
- Write/lifecycle Locust tests are disabled by default.

## Remaining Conditions Before AWS Staging Execution

1. Rerun `audit_performance_staging --strict` inside the deployed AWS staging environment and preserve the output.
2. Confirm AWS staging credentials cannot write to production databases, storage, queues or live GST providers.
3. Capture AWS staging database identity and service topology before the first staging load run.
4. Keep live GST filing/submission feature-gated until provider certification is separately completed.

## Executed Regression Pack

Command evidence: `docs/qa/evidence/p0-pre-staging/targeted_regressions_2026-10-12.txt`

Result:

- `Found 425 test(s).`
- `Ran 425 tests in 440.882s`
- `OK`

Covered suites:

- `reports.tests_accounting_truth_matrix`
- `reports.tests_books`
- `reports.tests_financial_trial_balance_exports`
- `reports.tests_financial_api_permissions`
- `reports.tests_receivables`
- `reports.tests_payables`
- `reports.tests_inventory`
- `reports.gstr1.tests.test_gstr1_report`
- `reports.gstr3b.tests.test_gstr3b_summary`
- `reports.gstr9.tests.test_gstr9_scaffold_api`
- `reports.tests_gst_portal`
- `reports.tests_gst_reconciliation`
- `reports.tests_gst_exception_dashboard`

## Final Verdict

**CONDITIONAL READY for AWS staging execution.**

The P0 local Docker launch gates are closed for financial correctness, GST report scope, provider safety configuration and backend export contracts. The condition is AWS-environment proof: because this certification did not access the deployed AWS stack, the strict safety audit and environment identity checks must be rerun there before staging performance or filing-adjacent testing begins.
