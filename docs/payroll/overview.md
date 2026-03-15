# Payroll Overview

## Purpose

The `payroll` app is Finacc's payroll transaction domain. It owns payroll setup, payroll runs, employee-level payroll results, payslips, approval flow, reversal flow, and payment handoff metadata.

It does **not** own accounting truth or treasury execution.

## Domain Boundaries

- `payroll` owns payroll workflow and payroll documents.
- `posting` owns normalized accounting entries and journal lines.
- `payments` owns disbursement execution and treasury lifecycle.
- `reports` owns read/query outputs.

Core rule:

`Payroll run != accounting entry`

Payroll calculates and approves business payroll results. Posting persists the accounting impact through the payroll posting adapter.

## What Exists Today

The payroll module now includes:

- enterprise-scoped payroll models
- effective-dated payroll configuration
- immutable approved and posted runs
- explicit reversal lineage
- separate payroll workflow status and payment status
- rollout validation and cutover tooling
- regression test coverage for workflow, posting, reversal, reconciliation, and commands

## Main Model Families

Configuration and setup:

- `PayrollComponent`
- `PayrollComponentPosting`
- `SalaryStructure`
- `SalaryStructureVersion`
- `SalaryStructureLine`
- `PayrollEmployeeProfile`
- `PayrollLedgerPolicy`
- `PayrollPeriod`

Operational runtime:

- `PayrollRun`
- `PayrollRunEmployee`
- `PayrollRunEmployeeComponent`
- `Payslip`
- `PayrollAdjustment`

Audit and workflow support:

- `PayrollRunActionLog`

## Main Services

- `PayrollRunService`: create, calculate, submit, approve, post, summary
- `PayrollRunHardeningService`: immutability, audit logging, payment state updates
- `PayrollReversalService`: reversal lineage and reversal posting
- `PayrollConfigResolver`: resolves effective-dated structure, posting, and policy config
- `PayrollPostingService`: payroll-to-posting handoff
- `PayrollPaymentService`: payroll-to-payments contract builder
- `PayrollRolloutValidationService`: rollout readiness checks
- `PayrollShadowRunService`: shadow-run validation
- `PayrollReconciliationService`: legacy/new parity and payroll self-consistency checks
- `PayrollPostingVerificationService`: posting quality verification
- `PayrollCutoverService`: go/no-go cutover validation

## Status Model

Payroll workflow status:

- `DRAFT`
- `CALCULATED`
- `APPROVED`
- `POSTED`
- `CANCELLED`
- `REVERSED`

Payment/disbursement status:

- `NOT_READY`
- `HANDED_OFF`
- `PARTIALLY_DISBURSED`
- `DISBURSED`
- `FAILED`
- `RECONCILED`

Important:

- `submit` records `submitted_by` and `submitted_at`, but does not introduce a separate `SUBMITTED` workflow status.
- accounting posting and payment execution are tracked separately by design.

## Where To Start

For backend developers:

1. Read [architecture.md](./architecture.md)
2. Read [workflows.md](./workflows.md)
3. Read [testing.md](./testing.md)

For finance operations and implementation:

1. Read [entity_onboarding.md](./entity_onboarding.md)
2. Read [rollout_runbook.md](./rollout_runbook.md)
3. Read [incident_runbook.md](./incident_runbook.md)
