# Purchase Statutory UAT Checklist

Date: 2026-05-08

## Purpose

This checklist is for validating the Purchase Statutory workspace before go-live or signoff.

It focuses only on:
- Purchase Statutory
- GSTR-2B match
- ITC register
- reconciliation
- challan lifecycle
- return lifecycle
- Form 16A / evidence handling

It does not replace the full purchase UAT.

## UAT Rules

- Use one entity, one financial year, and one subentity for the full run.
- Use one fixed review period unless a scenario explicitly needs another period.
- Record invoice number, challan number, return id, and batch id for every scenario.
- Capture screenshot and API error text for every failed step.
- If numbers mismatch, first verify purchase invoice truth before marking it as a statutory defect.

## Scope

Included:
- statutory dashboard and scope filters
- GSTR-2B import and matching
- ITC register visibility
- reconciliation exception visibility
- challan creation, approval, deposit, export
- return creation, approval, filing, export
- Form 16A issue, upload, and download flows
- review note and CA-style closure support

Excluded:
- purchase invoice data-entry UAT
- vendor onboarding UAT
- OCR and external integrations
- automated TRACES sync

## Signoff Conditions

Mark Purchase Statutory ready only if all are true:
- the workspace opens for the correct user roles
- filters work correctly for entity, financial year, subentity, tax type, and period
- GSTR-2B import works for valid input
- matching and mismatch review behave correctly
- ITC register reflects the underlying invoice state correctly
- challan workflow works end to end
- return workflow works end to end
- review notes and exports work
- the screen never behaves as a second source of truth for invoice tax values

## Suggested UAT Order

1. Access and scope
2. Overview and dashboard validation
3. GSTR-2B import and match
4. Reconciliation and ITC register
5. Challan workflow
6. Return workflow
7. Form 16A and evidence
8. Review note and exports

## Scenario Matrix

| ID | Scenario | Steps | Expected Result | Status |
|---|---|---|---|---|
| PS-01 | Screen access | Login with authorized statutory user and open Purchase Statutory | Screen opens successfully and shows current scope controls | Pending |
| PS-02 | Unauthorized access | Login with user without statutory access and try to open screen or API | Access is blocked cleanly | Pending |
| PS-03 | Scope filter apply | Change tax type, subentity, and period, then refresh workspace | Cards, lists, and tabs refresh for the selected scope only | Pending |
| PS-04 | Overview cards | Open Overview for active period | Deducted, deposited, filed, pending, and draft cards render without error | Pending |
| PS-05 | GSTR-2B import valid batch | Import one valid GSTR-2B batch | Batch is created and row count is correct | Pending |
| PS-06 | GSTR-2B batch rows | Open imported batch rows | Rows display correctly with supplier invoice details | Pending |
| PS-07 | GSTR-2B auto match | Run Auto Match on valid batch | Match summary returns correct totals and rows update | Pending |
| PS-08 | GSTR-2B manual review | Review one row manually and save match status/comment | Row review saves and status updates correctly | Pending |
| PS-09 | GSTR-2B mismatch case | Import row with wrong GSTIN/date/value | Row remains unmatched or partial with meaningful reason | Pending |
| PS-10 | Reconciliation exceptions | Open Reconciliation after mismatch scenario | Exception rows appear and point to likely fix area | Pending |
| PS-11 | ITC register visibility | Open ITC Register for mixed invoice cases | Eligible, blocked, pending, and mismatch outcomes display correctly | Pending |
| PS-12 | Review note save | Save a review note for the active period | Note saves and reopens correctly for same scope and period | Pending |
| PS-13 | Review note delete | Delete saved review note | Note is removed and no stale data remains | Pending |
| PS-14 | Challan draft manual create | Create challan manually with valid lines | Draft challan saves and appears in operations grid | Pending |
| PS-15 | Challan auto-populate | Create challan using eligible-line population | Eligible lines load correctly and totals match | Pending |
| PS-16 | Challan approval submit | Submit draft challan for approval | Approval state changes to submitted | Pending |
| PS-17 | Challan approval approve/reject | Approve or reject submitted challan | Workflow state updates correctly | Pending |
| PS-18 | Challan deposit | Deposit approved challan with CIN/BSR refs | Challan becomes deposited and references persist | Pending |
| PS-19 | Challan cancel control | Try allowed and disallowed cancel paths | Allowed cancel works; blocked cases show clear validation | Pending |
| PS-20 | Challan export | Export challans in available format | File downloads and content matches selected scope | Pending |
| PS-21 | Return draft manual create | Create return manually with valid lines | Draft return saves and appears in return grid | Pending |
| PS-22 | Return auto-populate | Create return using eligible-line flow | Lines load correctly and totals match | Pending |
| PS-23 | Return approval submit | Submit return for approval | Approval state changes to submitted | Pending |
| PS-24 | Return approval approve/reject | Approve or reject submitted return | Workflow state updates correctly | Pending |
| PS-25 | Return file | File approved return with filing details | Return becomes filed or revised and audit fields persist | Pending |
| PS-26 | Return cancel control | Try allowed and disallowed return cancel paths | Valid cancel works; blocked cases show clear validation | Pending |
| PS-27 | NSDL export | Export NSDL payload for valid return | Export works only when allowed and file content is generated | Pending |
| PS-28 | Form 16A issue | Issue Form 16A for eligible IT-TDS return | Issue record is created successfully | Pending |
| PS-29 | Form 16A official upload | Upload official document for a valid issue | File upload succeeds and issue record updates | Pending |
| PS-30 | Form 16A download | Download generated or uploaded Form 16A | Correct file downloads | Pending |
| PS-31 | CA pack export | Export CA pack for active period | Pack downloads with expected sheets/content | Pending |
| PS-32 | Data truth boundary | Attempt to use statutory screen to correct invoice tax truth | Workflow points user back to purchase invoice or master data, not direct statutory override | Pending |

## Validation Notes By Area

### Access

Validate:
- correct route access
- correct menu visibility
- correct API permission behavior

### GSTR-2B

Validate:
- batch create
- row visibility
- auto-match results
- manual review save
- mismatch reason clarity

### ITC and Reconciliation

Validate:
- visibility is scope-correct
- statuses are understandable
- exception guidance is meaningful

### Challans

Validate:
- draft creation
- approval workflow
- deposit
- cancellation rules
- export

### Returns

Validate:
- draft creation
- approval workflow
- filing
- revision behavior
- cancellation rules
- export

### Evidence

Validate:
- review notes
- CA pack
- Form 16A issue/upload/download

## Failure Logging Template

Use this for any failed case:

- Scenario ID:
- Scope used:
- Invoice / Batch / Challan / Return reference:
- User role:
- Step failed:
- Expected:
- Actual:
- Error text:
- Screenshot / payload:
- Root-cause guess:
  - access / RBAC
  - source invoice data
  - vendor / master
  - GSTR-2B import
  - ITC logic
  - challan workflow
  - return workflow
  - file / storage
  - export / document

## Final Signoff

- Purchase Statutory Overall: Pending
- GSTR-2B readiness: Pending
- ITC register readiness: Pending
- Challan workflow readiness: Pending
- Return workflow readiness: Pending
- Form 16A / evidence readiness: Pending
- Reporting / export readiness: Pending
- Business signoff owner: Pending
- CA signoff owner: Pending
