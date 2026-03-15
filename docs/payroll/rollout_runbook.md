# Payroll Rollout Runbook

## Purpose

This runbook is for engineering, finance operations, and implementation teams rolling payroll out to an entity.

The approved rollout pattern is:

- deploy schema first
- migrate only what matters
- validate in shadow mode
- cut over by entity and payroll period
- freeze legacy payroll before live cutover

## Phase 1: Staging Validation

1. Deploy payroll code and migrations to staging.
2. Apply migrations.
3. Validate payroll setup for the target entity.
4. Import legacy masters/config in dry-run mode if relevant.
5. Resolve all blocking setup issues before moving forward.

Recommended commands:

```bash
Finacc/venv/bin/python Finacc/manage.py validate_payroll_rollout_setup --entity <id> --entityfinid <id> --subentity <id> --period-code <code> --settings=FA.settings_test
Finacc/venv/bin/python Finacc/manage.py import_payroll_legacy_masters --entity <id> --entityfinid <id> --dry-run --settings=FA.settings_test
```

## Phase 2: Shadow Run

1. Create a non-live payroll run in the new payroll module for the comparison period.
2. Calculate the run.
3. Validate expected employee count.
4. Review exceptions such as missing config, missing profiles, or scope leakage.

Command:

```bash
Finacc/venv/bin/python Finacc/manage.py run_payroll_shadow_validation \
  --entity <id> \
  --entityfinid <id> \
  --subentity <id> \
  --run-id <payroll_run_id> \
  --expected-employee-count <count> \
  --settings=FA.settings_test
```

## Phase 3: Reconciliation

1. Compare legacy/source totals to the shadow run.
2. Validate:
   - employee count
   - gross
   - deductions
   - net pay
   - component totals
3. Review and explain all mismatches.

Command:

```bash
Finacc/venv/bin/python Finacc/manage.py reconcile_payroll_results \
  --run-id <payroll_run_id> \
  --legacy-json <legacy_snapshot.json> \
  --settings=FA.settings_test
```

## Phase 4: Posting and Reversal Validation

1. Approve and post a staging run.
2. Verify posting quality.
3. Reverse a posted run once in staging.
4. confirm reversal lineage and accounting reversal integrity.

Command:

```bash
Finacc/venv/bin/python Finacc/manage.py verify_payroll_posting --run-id <payroll_run_id> --settings=FA.settings_test
```

## Phase 5: Freeze Legacy Payroll

Before cutover:

- stop new legacy payroll processing for the target entity
- ensure no open approval items remain in legacy for the cutover period
- ensure no partly processed disbursement batch is still unresolved

This step is operationally mandatory.

## Phase 6: Cutover Validation

Run cutover validation only after:

- setup is complete
- shadow validation passed
- reconciliation passed
- legacy freeze is confirmed
- next payroll period exists in the new system

Command:

```bash
Finacc/venv/bin/python Finacc/manage.py validate_payroll_cutover \
  --entity <id> \
  --entityfinid <id> \
  --subentity <id> \
  --period-code <next_period_code> \
  --run-id <payroll_run_id> \
  --expected-employee-count <count> \
  --legacy-frozen \
  --settings=FA.settings_test
```

## Phase 7: Live Cutover

1. Use the next clean payroll period as the first live period.
2. Create run in the new payroll module.
3. Calculate.
4. Review.
5. Submit.
6. Approve.
7. Post.
8. Hand off to payments.
9. Reconcile payment execution.

## Stop Conditions

Do not cut over if any of these remain unresolved:

- blocking setup validation issue
- unresolved reconciliation mismatch
- missing posting map
- missing ledger policy
- scope inconsistency
- unresolved legacy freeze
- payment handoff contract not ready
