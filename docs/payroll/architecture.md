# Payroll Architecture

## Architectural Intent

Payroll is a transaction-domain module inside the Finacc monolith. It is intentionally separated from accounting persistence and payment execution.

The design goal is:

- payroll controls payroll workflow
- posting controls accounting truth
- payments controls disbursement
- reports read the correct source for the report type

## Hard Boundaries

### Payroll

Payroll owns:

- payroll components and configuration
- employee payroll setup
- payroll periods
- payroll runs
- employee run detail rows
- payslips
- approval metadata
- payment handoff metadata
- reversal lineage metadata

Payroll does not write accounting rows directly.

### Posting

Posting owns:

- posting batches
- entries
- journal lines
- accounting balance integrity
- accounting reporting source of truth

Payroll uses `posting/adapters/payroll_adapter.py` and `PayrollPostingService` to hand off approved payroll results into normalized accounting entries.

### Payments

Payments owns:

- treasury execution
- payment processing
- payout success/failure lifecycle
- reconciliation of actual payment execution

Payroll only tracks payment state and handoff references. It does not execute payment logic.

### Reports

Use payroll tables for:

- payroll operational reports
- payroll run summaries
- payslip access
- rollout/reconciliation validation

Use posting tables for:

- GL impact
- journal review
- accounting books and ledgers

## Scope Model

Scope discipline is a first-class rule.

### Required scope fields

Operational payroll documents:

- `entity`: required
- `entityfinid`: required where the document is period or accounting scoped
- `subentity`: nullable but scope-sensitive

Configuration objects are either:

- entity-scoped
- entity + financial year scoped
- entity + financial year + subentity scoped

### Practical scope rules

- `PayrollRun` must match `PayrollPeriod` scope exactly.
- `PayrollRunEmployee` rows must only be created from employee profiles inside the same run scope.
- component posting and ledger policy resolution must match run scope and effective date.
- cross-entity leakage is treated as a validation error, not a warning.

## Effective-Dated Configuration

Historical payroll runs must remain explainable even when config changes later.

That is why payroll uses:

- `SalaryStructureVersion`
- effective-dated `PayrollComponentPosting`
- effective-dated `PayrollLedgerPolicy`

At calculation time, payroll resolves active config by:

- scope
- run date
- approved version status

Then the resolved config is snapshotted onto the run and employee rows.

## Snapshot and Immutability Model

The snapshot spine is:

- `PayrollRun`
- `PayrollRunEmployee`
- `PayrollRunEmployeeComponent`

Approved and posted runs must not be silently changed.

Current hardening behavior:

- `calculate` creates snapshot rows
- `approve` freezes run and child rows
- `post` requires an immutable approved run
- further changes must happen through correction or reversal flow, not mutation

Snapshot context includes:

- resolved salary structure version
- resolved ledger policy version
- component posting version
- calculation assumptions
- config snapshot metadata on the run

## Reversal Design

Reversal does not rely on status alone.

The run model keeps explicit lineage:

- `reversed_run`
- `reversal_reason`
- `reversal_posting_entry_id`

`PayrollReversalService` creates a new reversal run and posts it separately. The original run is then marked `REVERSED`.

## Service-Layer Design

Views are transport only. Business rules live in services.

Key service responsibilities:

- `PayrollRunService`: run lifecycle
- `PayrollRunHardeningService`: freeze, audit logging, payment-state updates
- `PayrollReversalService`: reversal eligibility and lineage
- `PayrollConfigResolver`: effective-dated config lookup
- `PayrollPostingVerificationService`: posting quality checks
- `PayrollRolloutValidationService`: rollout setup readiness
- `PayrollCutoverService`: go/no-go cutover decision support

## Rollout and Migration Support

The payroll domain includes rollout tooling so new entities can be onboarded safely:

- setup validation
- shadow-run validation
- reconciliation against legacy snapshots
- posting verification
- cutover readiness validation
- management commands for repeatable rollout execution

See [rollout_runbook.md](./rollout_runbook.md) for the operational sequence.
