# Finacc Financial Statement Certification Gaps

Date: 2026-10-12  
Scope: P0 pre-staging financial statement closure  
Current state: **P0 financial-statement gate passed; remaining items are staging/P1 signoff**

## Statement Coverage Matrix

| Statement/report | P0 status | Independent proof |
|---|---|---|
| Trial Balance | PASS | Dataset A/B expected ledger closing balances and debit/credit totals. |
| Balance Sheet | PASS | Assets equal liabilities/equity with net profit carry-forward and zero difference. |
| Profit & Loss | PASS | Service and trading profit independently calculated from source flows. |
| Trading Account | PASS | Purchases, returns, sales, returns, FIFO closing stock and gross profit reconciled. |
| General Ledger / Ledger Summary | PASS | Ledger-level balances reconcile to Trial Balance, GST, AR/AP and bank/cash movement. |
| Daybook | PASS | Active posted transaction count and totals validated; draft/reversed entries excluded. |
| Cash Book | PASS / P1 UX | Cash ledger value verified through posted transfer; dedicated report UI/export parity remains P1. |
| Bank Book | PASS / P1 UX | Bank ledger value verified through opening, receipt, payment, freight and transfer movements; dedicated report UI/export parity remains P1. |
| Receivables | PASS | Open items, settlements and customer ledger closure reconcile. |
| Payables | PASS | Vendor bills, settlements and vendor ledger closure reconcile. |
| Inventory valuation | PASS | FIFO closing quantity/value and trading account stock tie-out verified. |
| GST statements | PASS | GSTR1/GSTR3B/GSTR9 scoped evidence and GST portal safety tests included. |

## Remaining Gaps

| Priority | Gap | Status | Required closure |
|---|---|---|---|
| P0 | AWS staging external integration proof | Conditional | Rerun strict audit inside deployed AWS staging. |
| P1 | Browser/PDF/print parity for every visible critical report | Open | Validate rendered PDF/print/download outputs in staging. |
| P1 | Live GST filing/submission | Excluded from launch scope unless separately certified | Keep feature-gated or disabled; certify provider sandbox before enablement. |
| P1 | Dedicated Cash Book and Bank Book export tests | Open | Tie dedicated report outputs to truth-pack cash/bank ledger values. |
| P2 | Additional FY-close/amendment-heavy GST scenarios | Open | Add after AWS staging baseline and P1 export closure. |

## GSTR9 Disposition

GSTR9 is suitable for AWS staging as a reporting/export/freeze/manual/simulated filing workflow. It should not be treated as certified for live automated filing/submission. The launch-safe posture is:

- Enable report summary, table drilldowns, validation, freeze/history and JSON/CSV/XLSX exports.
- Allow manual/simulated filing flows for staging certification.
- Keep live provider submission disabled unless a separate provider certification explicitly passes.

## Final Gap Verdict

No remaining P0 financial-statement calculation blocker was identified in the local Docker evidence. AWS staging remains conditional on environment-level safety proof and re-execution of the targeted P0 pack in the deployed context.

