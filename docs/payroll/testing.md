# Payroll Testing

## Test Suite Scope

Payroll has a dedicated regression suite under `payroll/tests`.

Current coverage includes:

- model and constraint checks
- payroll run lifecycle
- reversal flow
- payment handoff and payment reconciliation
- payroll posting adapter behavior
- posting verification service
- reconciliation service
- rollout validation service
- cutover validation service
- management commands

## Main Test Files

- `payroll/tests/test_models.py`
- `payroll/tests/test_payroll_run_service.py`
- `payroll/tests/test_payroll_reversal_service.py`
- `payroll/tests/test_payroll_payment_service.py`
- `payroll/tests/test_payroll_posting_adapter.py`
- `payroll/tests/test_payroll_reconciliation_service.py`
- `payroll/tests/test_payroll_rollout_validation_service.py`
- `payroll/tests/test_payroll_cutover_service.py`
- `payroll/tests/test_management_commands.py`
- `payroll/tests/factories.py`

## How To Run Payroll Tests

Run the payroll suite:

```bash
Finacc/venv/bin/python Finacc/manage.py test payroll.tests --settings=FA.settings_test
```

Run a single test module:

```bash
Finacc/venv/bin/python Finacc/manage.py test payroll.tests.test_payroll_run_service --settings=FA.settings_test
```

## What The Suite Protects

The current suite is intended to catch regressions in:

- workflow transition rules
- immutability behavior
- scope discipline
- reversal lineage
- payment lifecycle separation
- posting adapter correctness
- rollout and cutover guardrails
- command failure behavior

## Adding Tests For New Payroll Features

When adding a new payroll feature:

1. add service-level tests first
2. add failure-path tests
3. add scope mismatch tests if the feature is scope-sensitive
4. add posting/reconciliation tests if the feature affects accounting
5. add command tests if rollout tooling changes

Good rule:

- every new workflow action should have a happy-path test and at least one blocking-failure test

## Release Expectation

Before releasing payroll changes:

- run the payroll test suite
- run rollout validation commands in staging if rollout code changed
- re-check reversal flow if posting logic changed
- re-check payment handoff/reconcile behavior if payment boundary changed

## Test Environment Note

Posting-related tests stub the Postgres advisory lock during SQLite test runs. This keeps the suite portable under `FA.settings_test` while still exercising payroll posting behavior.
