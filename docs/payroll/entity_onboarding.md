# Entity Onboarding

## Goal

Use this guide when enabling payroll for a new entity in Finacc.

Do not start live payroll processing until rollout validation passes for that entity.

## Required Setup Checklist

### 1. Scope and control prerequisites

Confirm:

- target `entity` exists
- target `entityfinid` exists
- target `subentity` strategy is defined
- payroll ownership and approver roles are known

### 2. Payroll components

Create entity-scoped payroll components for:

- earnings
- deductions
- employer contributions
- reimbursements
- recoveries

For each component define:

- `code`
- `name`
- `component_type`
- `posting_behavior`
- tax/statutory metadata if relevant

### 3. Salary structures

Create:

- `SalaryStructure`
- at least one approved `SalaryStructureVersion`
- `SalaryStructureLine` rows

Good practice:

- do not edit active structure logic in place
- create a new structure version for payroll rule changes

### 4. Employee payroll profiles

Create `PayrollEmployeeProfile` rows with:

- correct entity/subentity assignment
- employee code
- salary structure assignment
- structure version assignment if used directly
- payment account
- payroll-active status

### 5. Ledger policy

Create a scoped `PayrollLedgerPolicy` with:

- salary payable account
- optional payroll clearing account
- optional reimbursement and employer contribution payable accounts
- version number
- effective date

### 6. Component posting mappings

Create `PayrollComponentPosting` rows for all payroll components used by the entity.

Each posting row should define:

- expense account if applicable
- liability account if applicable
- payable account if applicable
- version number
- effective date

### 7. Payroll periods

Create an `OPEN` payroll period for the first live payroll cycle:

- period code
- period start
- period end
- payout date
- frequency

### 8. Numbering and policy prerequisites

If document numbering is used:

- ensure payroll document type `PRUN` is configured

If approval policy is organization-specific:

- confirm approver access is in place before live use

## Validation Commands Before Go-Live

Run setup validation:

```bash
Finacc/venv/bin/python Finacc/manage.py validate_payroll_rollout_setup \
  --entity <entity_id> \
  --entityfinid <entityfinid_id> \
  --subentity <subentity_id> \
  --period-code <period_code> \
  --settings=FA.settings_test
```

Run shadow validation:

```bash
Finacc/venv/bin/python Finacc/manage.py run_payroll_shadow_validation \
  --entity <entity_id> \
  --entityfinid <entityfinid_id> \
  --subentity <subentity_id> \
  --run-id <payroll_run_id> \
  --expected-employee-count <count> \
  --settings=FA.settings_test
```

Run cutover validation:

```bash
Finacc/venv/bin/python Finacc/manage.py validate_payroll_cutover \
  --entity <entity_id> \
  --entityfinid <entityfinid_id> \
  --subentity <subentity_id> \
  --period-code <period_code> \
  --run-id <payroll_run_id> \
  --expected-employee-count <count> \
  --legacy-frozen \
  --settings=FA.settings_test
```

## Go-Live Gate

Do not mark an entity ready for live payroll until:

- setup validation passes
- shadow run passes
- reconciliation is within tolerance
- posting verification passes
- finance signs off the first comparison pack
- legacy payroll is frozen for the cutover period
