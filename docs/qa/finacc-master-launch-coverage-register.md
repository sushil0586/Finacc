# Finacc Master Launch Coverage Register

Date: 2026-10-12  
Scope: pre-staging P0 launch coverage closure  
Verdict: **Conditional Ready for AWS staging execution**

## Coverage Summary

| Area | Status | Evidence |
|---|---|---|
| Trial Balance | PASS | Independent truth-pack datasets validate closing debit/credit equality, ledger balances, opening balances, party closure and GST ledger balances. |
| Balance Sheet | PASS | Dataset A and B verify assets equal liabilities/equity and net profit carry-forward. |
| Profit & Loss | PASS | Dataset A service net profit `6000.00`; Dataset B trading net profit `4800.00`. |
| Trading Account | PASS | Dataset B verifies FIFO inventory quantity/value, closing stock and gross profit. |
| General Ledger / Ledger Summary | PASS | Ledger balances reconcile to Trial Balance and GST ledgers. |
| Cash/Bank Book | PASS | Bank/cash ledger movements are represented through posted entries and Daybook/Ledger Summary; dedicated UI/export signoff remains P1. |
| Daybook | PASS | Active posted transactions, totals and draft/reversed exclusion verified. |
| Receivables | PASS | Open items, settlements and customer ledger closure verified. |
| Payables | PASS | Vendor open items, settlements and vendor ledger closure verified. |
| Inventory valuation | PASS | FIFO valuation and negative-stock valuation behavior covered by tests. |
| GST reports | PASS | GSTR1, GSTR3B, reconciliation, exception dashboard and GSTR9 scaffold/API suites included in targeted regression scope. |
| GSTR9 | PASS WITH SCOPE | Report/export/freeze/manual/simulated workflows certified for staging; live automated provider submission excluded. |
| GST filing/provider routes | PASS FOR LOCAL DOCKER | Strict safety audit verifies sandbox/disabled external financial side effects; AWS rerun required. |
| Exports | PASS / CONDITIONAL UI | Backend critical exports covered; final browser PDF/print layout remains P1 manual signoff. |
| Tenant isolation / RBAC | PASS | Financial API permissions and GSTR9 export/action restrictions included in targeted tests. |
| Performance evidence | PASS WITH CONDITIONS | Phase 2C local Docker evidence supports staging entry, not production capacity claims. |

## P0 Gate Register

| P0 gate | Status | Closure criteria | Result |
|---|---|---|---|
| Financial-statement truth pack | PASS | Independently expected accounting values across statements, not journal balance alone. | Two disposable truth-pack datasets cover service and trading flows. |
| GSTR9 launch disposition | PASS WITH SCOPE | Certify or exclude with feature gating. | Certify staging report/export/freeze/manual/simulated scope; exclude live automated filing. |
| External provider safety | PASS FOR LOCAL DOCKER; AWS RERUN REQUIRED | Prove no live GST/provider/email/storage side effects. | Docker strict audit passed; deployed AWS environment must run the same audit. |
| Export parity | PASS / CONDITIONAL UI | Critical API/export totals and formats validated. | Backend export contracts pass; PDF/print visual signoff remains P1. |

## Launch Gap Register

| Priority | Gap | Owner | Closure trigger |
|---|---|---|---|
| P0 | AWS staging safety audit not yet captured in this local run. | DevOps / QA | Run strict audit in AWS and archive database/provider/storage identity evidence. |
| P1 | Browser-level PDF/print layout parity for critical financial reports. | QA / Product | Manual or Playwright output review on AWS staging. |
| P1 | Live automated GST provider submission certification. | Compliance / Engineering | Provider sandbox certification, approval workflow, and explicit production feature gate. |
| P1 | Cash Book / Bank Book dedicated report export UX parity. | QA | Verify filters, totals and exports against truth-pack values. |
| P2 | Wider rare-period workflows such as FY close and amendment-heavy GST periods. | QA | Add targeted staging scenarios after AWS baseline is stable. |

## Recommended Next Execution Order

1. Run AWS staging strict safety audit and database identity proof.
2. Re-execute targeted P0 regression pack against AWS staging or a staging-mirrored disposable database.
3. Perform export/PDF visual parity signoff for Trial Balance, Balance Sheet, P&L, Trading Account, Ledger, Daybook, Cash/Bank Book, receivables/payables and GST.
4. Keep live GST filing disabled until a separate provider certification passes.

