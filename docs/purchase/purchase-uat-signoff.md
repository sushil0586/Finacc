# Purchase UAT Signoff

Date: 2026-04-06

Purpose:
- validate Purchase end to end for GST, ITC, TDS, challan, return, attachments, and TRACES certificate flow
- confirm purchase invoice remains the source of truth
- capture pass/fail cleanly before broader tax UAT

## UAT Rules

- Use one test entity and subentity for the full run.
- Keep one fixed period for the scenario set.
- Record invoice number / challan number / return id for every scenario.
- If a scenario fails, note:
  - exact step
  - actual result
  - screenshot or API error
  - whether it is source-data issue, posting issue, or statutory issue

## Scope

Included:
- purchase invoice tax truth
- GST
- ITC
- GSTR-2B
- invoice-based TDS
- challan lifecycle
- return lifecycle
- purchase attachments
- TRACES Form 16A archival flow

Excluded:
- vendor bill attachment OCR/extraction
- automated TRACES integration

## Signoff Criteria

Mark Purchase signoff only if all are true:
- invoice tax values save correctly
- posting follows invoice truth
- statutory screens reflect operational state correctly
- challan lifecycle works
- return lifecycle works
- attachments work
- TRACES certificate archival works
- no screen behaves like a second tax source of truth

## Scenario Matrix

| ID | Scenario | Steps | Expected Result | Status |
|---|---|---|---|---|
| P-01 | Goods invoice with GST | Create goods purchase invoice with GST lines, save, confirm/post | GST values persist; invoice reopens with same values; posting succeeds | Pending |
| P-02 | Service invoice with GST | Create service purchase invoice with GST lines, save, confirm/post | GST values persist; service invoice behaves same as goods flow | Pending |
| P-03 | Invoice-based TDS | Create purchase invoice with TDS enabled and valid section | TDS base/rate/amount save on invoice; invoice is source of truth | Pending |
| P-04 | Default TDS section behavior | Create invoice where default TDS section should apply | Default section appears correctly or validation explains what is missing | Pending |
| P-05 | Payment-stage boundary | Open payment voucher against invoice-based TDS case | Runtime TDS does not act as second truth; boundary message is clear | Pending |
| P-06 | GST-TDS invoice case | Create invoice with GST-TDS relevant setup | GST-TDS values/posting/statutory visibility are correct | Pending |
| P-07 | RCM case | Create purchase invoice flagged for RCM | RCM values persist and posting reflects payable behavior correctly | Pending |
| P-08 | Blocked ITC case | Create invoice with blocked ITC setup | ITC register shows blocked/ineligible outcome with meaningful reason | Pending |
| P-09 | ITC claim-ready case | Create eligible invoice and review ITC register | ITC row shows eligible/claim-ready path correctly | Pending |
| P-10 | GSTR-2B import | Import one valid GSTR-2B batch | Batch saves; rows load in UI; cards update | Pending |
| P-11 | GSTR-2B match success | Auto-match row that should match one invoice | Row matches invoice; status and reason update correctly | Pending |
| P-12 | GSTR-2B mismatch | Import row with GSTIN/date/value mismatch | Row remains unmatched/partial; UI explains likely fix area | Pending |
| P-13 | Reconciliation exceptions | Open reconciliation after mismatch scenario | Exception rows appear; fix guidance points back to invoice/master/posting as appropriate | Pending |
| P-14 | Attachment upload | Upload attachment on purchase invoice | Upload succeeds; attachment visible in popup and reload | Pending |
| P-15 | Attachment download/delete | Download and delete uploaded attachment | File downloads; delete removes row; reload stays consistent | Pending |
| P-16 | Challan draft create | Create challan draft manually | Draft saves with lines; appears in Challan Ops | Pending |
| P-17 | Challan one-click draft | Use one-click draft | Draft is created with eligible lines and correct totals | Pending |
| P-18 | Challan approval flow | Submit, approve, reject on draft challan | Workflow states and buttons behave correctly | Pending |
| P-19 | Challan deposit | Deposit approved challan | Challan becomes deposited; date/CIN/BSR/bank refs persist | Pending |
| P-20 | Challan export | Download challan filing pack/export | Download works and content aligns with selected row/scope | Pending |
| P-21 | Return draft create | Create return draft manually | Draft saves with eligible lines and appears in Returns | Pending |
| P-22 | Return one-click draft | Use one-click return creation | Draft created with correct tax type/period lines | Pending |
| P-23 | Return approval flow | Submit, approve, reject on draft return | Workflow states and buttons behave correctly | Pending |
| P-24 | Return file | File approved return | Filed date/ack/arn save; row moves to filed/revised state | Pending |
| P-25 | NSDL export | Download NSDL after filing | Download only enabled for filed/revised return; file downloads correctly | Pending |
| P-26 | TRACES 16A open | Open TRACES 16A for eligible filed IT-TDS return | Deductee-wise grouped certificate rows open correctly | Pending |
| P-27 | TRACES 16A upload | Upload TRACES PDF against one deductee group | Upload succeeds; row status updates | Pending |
| P-28 | TRACES 16A download | Download uploaded TRACES PDF | Correct file downloads for selected deductee group | Pending |
| P-29 | Credit note impact | Create purchase credit note linked to prior invoice | GST/TDS/ITC impact reflects correctly in purchase/statutory views | Pending |
| P-30 | Debit note impact | Create purchase debit note linked to prior invoice | GST/TDS/ITC impact reflects correctly in purchase/statutory views | Pending |
| P-31 | Cancelled challan behavior | Cancel a valid draft/non-linked challan where allowed | Challan moves to cancelled; audit trail remains; invalid cancel cases are blocked | Pending |
| P-32 | Cancelled return behavior | Cancel a valid return where allowed | Return moves to cancelled; revision history retained | Pending |

## Suggested Execution Order

1. Invoice truth
2. GST / ITC / GSTR-2B
3. Attachments
4. Challan lifecycle
5. Return lifecycle
6. TRACES certificate flow
7. Notes / cancellation edge cases

## Observation Template

Use this for any failed row:

- Scenario ID:
- Invoice / Challan / Return reference:
- Step failed:
- Expected:
- Actual:
- Error text:
- Screenshot/API payload:
- Root cause guess:
  - source invoice
  - vendor/master
  - posting
  - statutory workflow
  - attachment/storage
  - certificate flow

## Final Verdict

- Purchase UAT Overall: Pending
- GST readiness: Pending
- ITC readiness: Pending
- TDS readiness: Pending
- Challan readiness: Pending
- Return readiness: Pending
- Attachment readiness: Pending
- TRACES archival readiness: Pending
