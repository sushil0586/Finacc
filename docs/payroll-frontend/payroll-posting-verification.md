# Payroll Posting Verification

Use the project virtual environment from the Django app root and do not use the system interpreter for payroll posting verification.

## Working Directory

Run these commands from:

```bash
/Users/ansh/finacc-angular/finacc-django/Finacc
```

## Venv Setup

Create or refresh the local backend venv with:

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

Quick sanity check:

```bash
./venv/bin/python -V
./venv/bin/python -c "import django, decouple; print(django.get_version())"
```

## Verification Commands

Run the exact backend verification commands with payroll tests enabled:

```bash
ENABLE_PAYROLL_IN_TESTS=1 ./venv/bin/python manage.py check
ENABLE_PAYROLL_IN_TESTS=1 ./venv/bin/python manage.py test payroll.tests.test_payroll_posting_finalization --keepdb --noinput -v 2
```

## What This Covers

- Journal preview stays balanced.
- Missing component or static account mappings fail validation.
- Statutory payable lines resolve through static account mappings.
- FnF preview uses snapshot-driven payable or recoverable rows.
- Posting remains compatible with reversal flows.
- Posting does not trigger payroll recalculation.

## Notes

- If Django reports conflicting migrations in `posting`, make sure the chain includes `0023_seed_payroll_static_accounts` and `0024_alter_entry_txn_type_alter_inventorymove_txn_type_and_more`.
- If the test run reports missing packages, reinstall from `requirements.txt` with `./venv/bin/python -m pip install -r requirements.txt`.
- `--keepdb` is intentional so repeat verification runs stay fast and stable.
