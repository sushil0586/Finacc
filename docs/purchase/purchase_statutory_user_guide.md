# Purchase Statutory User Guide

Date: 2026-05-08

## Purpose

This guide explains the Purchase Statutory workspace in simple business language.

Use this module to:
- review purchase-side tax compliance
- reconcile purchase invoices with statutory data
- track ITC status
- manage purchase TDS and GST-TDS challans
- prepare and file statutory returns
- keep review evidence ready for finance and CA signoff

This screen is a working control room.

It is not the original source of tax truth.

The purchase invoice remains the main source of truth for:
- GST values
- TDS values
- GST-TDS values
- vendor tax details
- invoice-level tax corrections

If statutory numbers look wrong, first check the purchase invoice and vendor master.

## Who Should Use It

- Accounts Payable team: to monitor deductions, create drafts, and complete regular workflow steps
- Tax/Compliance team: to review challans, returns, mismatches, and filing evidence
- Finance Controller / CA: to review exceptions, closure notes, and export packs

## What You Need Before Using It

Before using Purchase Statutory, make sure:
- purchase invoices are entered correctly
- vendor PAN, GSTIN, and tax setup are maintained
- the correct entity, financial year, and subentity are selected
- invoice posting is completed where your process requires it
- the team knows whether it is working on IT-TDS or GST-TDS

## Main Screen Sections

The Purchase Statutory workspace is split into six practical sections.

### 1. Overview

Use this section first.

It gives a quick picture of:
- deducted amount
- deposited amount
- filed amount
- pending deposit
- pending filing
- draft challans
- draft returns

It also shows:
- reporting shortcuts
- CA signoff cues
- payment-voucher TDS readiness

Best use:
- daily monitoring
- month-end review
- management summary

### 2. GSTR-2B Match

Use this section to compare supplier GST data with purchase invoices.

Typical actions:
- import GSTR-2B rows
- review import batches
- open batch rows
- run auto-match
- review mismatches manually

Best use:
- monthly GST purchase reconciliation
- missing invoice detection
- vendor GST mismatch follow-up

### 3. Reconciliation

Use this section to understand why books and statutory views do not align.

Typical outputs:
- exception rows
- mismatch reasons
- guidance on what to fix

Best use:
- pre-filing clean-up
- CA review
- internal control follow-up

### 4. ITC Register

Use this section to review Input Tax Credit status.

Typical outcomes:
- eligible
- blocked
- pending
- mismatched

Best use:
- GST closing review
- blocked ITC checks
- invoice follow-up before return preparation

### 5. Challan Ops

Use this section for purchase-side TDS and GST-TDS payment workflow.

Typical actions:
- create challan draft
- auto-populate eligible lines
- submit for approval
- approve or reject
- deposit challan
- export challan data

Best use:
- operational payment tracking
- tax deposit workflow

### 6. Returns

Use this section for statutory return preparation and filing.

Typical actions:
- create return draft
- auto-pick eligible lines
- submit for approval
- approve or reject
- file return
- export NSDL payload where relevant
- manage Form 16A / supporting evidence where applicable

Best use:
- period-end filing
- revision handling
- proof and archive management

## Recommended Monthly Working Flow

Follow this order for the smoothest process.

### Step 1. Set the Scope

At the top of the screen, choose:
- tax type
- subentity if needed
- date from
- date to

Use the same scope for the full review cycle.

This avoids confusion between invoices, challans, and returns.

### Step 2. Check Overview

Review the dashboard cards first.

Focus on:
- pending deposit
- pending filing
- draft challans
- draft returns
- any warning or next-step hint shown on screen

If the overview looks wrong, do not jump directly to return filing.
First check invoice accuracy and mismatches.

### Step 3. Complete GSTR-2B Match

If you are doing GST compliance:
- import the GSTR-2B batch for the month
- open the imported rows
- run Auto Match
- review unmatched or partial rows

If a row does not match:
- check vendor GSTIN
- check supplier invoice number
- check invoice date
- check taxable and tax amounts
- confirm the purchase invoice exists in the same entity and period

Do not manually force a match until the invoice/master data issue is understood.

### Step 4. Review Reconciliation Exceptions

Open the Reconciliation section and review all exception rows.

Use this section to answer:
- what is missing?
- what is mismatched?
- what must be corrected before closure?

Typical fixes happen in:
- purchase invoice
- vendor master
- posting flow
- challan / return workflow

### Step 5. Review ITC Register

Open ITC Register and verify:
- eligible ITC rows
- blocked ITC rows
- pending / mismatched rows

This step is important before GST filing and before final CA review.

### Step 6. Create Challan Drafts

Go to Challan Ops when deduction has happened and deposit is due.

You can:
- create a challan manually, or
- auto-populate eligible lines for the selected period

Before saving, confirm:
- tax type is correct
- period is correct
- selected invoices are correct
- deposit references are ready if already available

### Step 7. Submit and Approve Challans

If your company uses maker-checker:
- creator submits
- approver reviews
- approver approves or rejects

If rejected:
- open the challan
- review remarks
- correct the issue
- resubmit

### Step 8. Deposit Challan

Once approval is complete, record deposit details such as:
- deposit date
- bank reference
- BSR code
- CIN number
- other payment details

Only deposit after confirming the payment actually happened.

### Step 9. Create Return Draft

After deposit and reconciliation:
- create the return draft
- use eligible-line logic if available
- verify return code, period, and tax type

Check the rows carefully before moving forward.

### Step 10. Submit, Approve, and File Return

Complete the return workflow in this order:
- draft
- submit
- approve
- file

At the filing stage, capture:
- filing date
- acknowledgement number
- ARN where applicable
- supporting attachment if used by your process

### Step 11. Export and Archive Evidence

After filing:
- download exports
- create CA pack if needed
- use Form 16A / proof tracking where applicable
- save the reviewer closure note

This step is important for audit trail and period closure.

## Practical Meaning of Each Status

### Draft

The item is created but not yet finalized.

### Submitted

The item is sent for approval.

### Approved

The item is approved internally and is ready for the next step.

### Deposited

The challan payment has been recorded.

### Filed

The statutory return has been filed.

### Rejected

The item needs correction before it can move forward.

### Cancelled

The item is no longer active and should not be used for current filing.

## Common Business Mistakes

Avoid these mistakes:

- treating statutory screens as the place to fix invoice tax values
- using the wrong period or tax type in the workspace filter
- creating challans before reviewing eligible invoices
- filing returns before challan deposit is fully recorded
- ignoring partial or unmatched GSTR-2B rows
- skipping review notes and evidence capture
- mixing multiple branches or subentities in one review run

## Where To Fix Problems

Use this quick rule:

- invoice tax amount wrong: fix the purchase invoice
- vendor GSTIN or PAN wrong: fix vendor master
- GSTR-2B mismatch: check invoice details and supplier data
- challan total wrong: review eligible line selection
- return total wrong: review challan links and filing scope
- CA observation pending: use review note and exception tracking

## Best Practices

- Keep one fixed date range for the full month-end review
- Finish invoice corrections before statutory closure
- Resolve GSTR-2B mismatches before final ITC decisions
- Use challan drafts as working papers, not as final truth
- Capture filing references immediately after filing
- Save review notes for each closure cycle
- Export evidence before month-end signoff

## Suggested Team Ownership

- AP Executive:
  invoice clean-up, batch import, draft creation
- Tax Executive:
  reconciliation, ITC review, challan and return preparation
- Approver / Manager:
  approval, filing signoff, exception clearance
- CA / Finance Head:
  final review, evidence check, closure note review

## Simple FAQ

### Why is a value wrong in Purchase Statutory?

Usually because the purchase invoice, vendor tax data, or source posting is wrong.

### Can I correct tax values directly here?

No. This workspace is mainly for review, workflow, and filing operations.

### What should I do first each month?

Set scope, review Overview, then complete GSTR-2B and reconciliation.

### When should challan be created?

After verifying the deducted amount and eligible invoice lines for the period.

### When should return be filed?

Only after reconciliation is reviewed and challan/payment data is complete.

### Why should I save review notes?

They help with CA review, internal signoff, and future audit trail.

## Final Business Summary

Purchase Statutory is the compliance workspace for turning purchase-side tax data into a controlled filing process.

The safe operating sequence is:

1. keep invoice truth correct
2. reconcile supplier and invoice data
3. review ITC and exceptions
4. create and deposit challans
5. prepare and file returns
6. save proof and review notes

If users follow this order, the module becomes much easier to operate and much safer at month end.
