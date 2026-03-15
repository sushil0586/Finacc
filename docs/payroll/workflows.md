# Payroll Workflows

## Workflow Overview

The payroll runtime workflow is:

1. create run
2. calculate run
3. submit run
4. approve run
5. post run
6. hand off to payments
7. reconcile payment status
8. reverse if required

## Payroll Workflow Status

Run status values:

- `DRAFT`
- `CALCULATED`
- `APPROVED`
- `POSTED`
- `CANCELLED`
- `REVERSED`

Important implementation detail:

- `submit` does not change the status to a separate submitted value.
- it records submission metadata and an audit action while the run remains in `CALCULATED`.

## Payment Status

Payment status values:

- `NOT_READY`
- `HANDED_OFF`
- `PARTIALLY_DISBURSED`
- `DISBURSED`
- `FAILED`
- `RECONCILED`

Payment status is independent from payroll posting status.

## Standard Run Lifecycle

### 1. Create Run

Service:

- `PayrollRunService.create_run`

Requirements:

- payroll period exists
- period is `OPEN`
- run scope matches period scope

Output:

- run created in `DRAFT`
- numbering assigned if numbering is configured
- action log row created

### 2. Calculate Run

Service:

- `PayrollRunService.calculate_run`

Requirements:

- run is mutable
- status is `DRAFT` or `CALCULATED` with `force=True`
- active payroll ledger policy exists for scope/date

What happens:

- active employee profiles are resolved within the run scope
- salary structure version is resolved per employee
- component posting version is resolved per component
- employee rows and component snapshot rows are rebuilt
- run totals and config snapshot are updated
- run status becomes `CALCULATED`

### 3. Submit Run

Service:

- `PayrollRunService.submit_run`

Requirements:

- status is `CALCULATED`

What happens:

- `submitted_by` and `submitted_at` are set
- optional comment and reason code are stored
- action log row is created

### 4. Approve Run

Service:

- `PayrollRunService.approve_run`

Requirements:

- status is `CALCULATED`
- employee rows exist

What happens:

- status becomes `APPROVED`
- approver metadata is recorded
- immutability is enforced
- employee rows and component rows are frozen
- action log row is created

### 5. Post Run

Service:

- `PayrollRunService.post_run`

Requirements:

- status is `APPROVED`
- run is immutable

What happens:

- payroll posting adapter builds normalized posting inputs
- `posting` persists the accounting entry
- run status becomes `POSTED`
- `posted_entry_id` and `post_reference` are stored
- action log row is created

## Payment Workflow

### 6. Payment Handoff

Service:

- `PayrollRunHardeningService.handoff_payment`

Requirements:

- run status is `POSTED`

What happens:

- payment status becomes `HANDED_OFF`
- `payment_batch_ref` and handoff payload are stored
- employee-row payment status is updated
- action log row is created

### 7. Payment Reconciliation

Service:

- `PayrollRunHardeningService.reconcile_payment`

Requirements:

- payment handoff has already happened in normal operations

What happens:

- payment status is updated to one of:
  - `PARTIALLY_DISBURSED`
  - `DISBURSED`
  - `FAILED`
  - `RECONCILED`
- employee-row payment status is updated
- action log row is created

## Reversal Workflow

### 8. Reverse Run

Service:

- `PayrollReversalService.reverse_run`

Requirements:

- original run status is `POSTED`
- no prior reversal run already exists

What happens:

- a new reversal run is created
- reversal run is linked to the original through `reversed_run`
- reversal run is posted separately through the posting adapter
- original run is marked `REVERSED`
- reversal reason and lineage are preserved

## Invalid Transition Rules

These transitions must fail:

- post without approval
- calculate immutable run
- reverse non-posted run
- payment handoff before posting
- cross-scope employee/profile inclusion
- config resolution without valid policy scope/date

## Safe Operational Guidance

- do not modify approved or posted runs directly
- do not hand-edit payroll totals after calculation
- do not treat payment completion as a posting event
- do not reverse by deleting rows; always use reversal flow
- do not run payroll across period boundaries without a new payroll period
