# Payroll Incident Runbook

## Purpose

Use this runbook when payroll processing, posting, payment handoff, or cutover validation fails.

## Failed Calculation

Typical symptoms:

- calculation endpoint returns validation error
- run remains `DRAFT`
- no employee rows created

Check:

- payroll period is `OPEN`
- ledger policy exists for scope/date
- active employee profiles exist in the run scope
- salary structure version is approved and effective
- component posting mappings exist

Useful commands:

- `validate_payroll_rollout_setup`
- `run_payroll_shadow_validation`

## Posting Mismatch

Typical symptoms:

- post fails
- `posted_entry_id` missing
- posting verification fails

Check:

- run is `APPROVED`
- run is immutable
- payroll posting adapter is resolving accounts correctly
- journal lines are balanced
- salary payable and liability accounts are configured

Useful command:

- `verify_payroll_posting`

## Payment Mismatch

Typical symptoms:

- payment status does not match treasury outcome
- handoff succeeded but finance sees missing payout

Check:

- `payment_batch_ref`
- `payment_handoff_payload`
- payments-side execution status
- whether payroll status is correctly still `POSTED`

Important:

- do not use payroll status to infer treasury completion
- use payment status and payment system evidence

## Scope Mismatch

Typical symptoms:

- wrong employees appear in a run
- setup validation flags missing scoped config
- cross-branch data appears unexpectedly

Check:

- `entity`
- `entityfinid`
- `subentity`
- employee profile scope
- payroll period scope
- component posting scope
- ledger policy scope

## Reversal Issues

Typical symptoms:

- reversal attempt fails
- multiple reversal attempts
- accounting reversal not linked

Check:

- original run is `POSTED`
- no prior reversal run exists
- reversal posting completed
- original run now shows `REVERSED`

Never fix reversal problems by deleting posted rows manually.

## Cutover Blocked

Typical symptoms:

- cutover validator returns failure
- finance refuses go-live because parity is not proven

Check:

- setup validation result
- shadow validation result
- reconciliation result
- legacy freeze confirmation
- next payroll period readiness

## Escalation Rule

Escalate to engineering plus finance owner if:

- a posted run appears wrong
- a reversal fails after posting
- payment status and treasury outcome disagree
- entity scope leakage is suspected
