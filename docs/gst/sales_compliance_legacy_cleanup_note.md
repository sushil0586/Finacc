# Sales Compliance Legacy Cleanup Note

## Purpose

Record the current state of the sales compliance persistence layer after the WhiteBooks/provider refactor work, and identify which models/tables are:

- active runtime dependencies
- compatibility-only
- likely cleanup candidates for a later migration phase

This note is intentionally scoped to the sales compliance path:

- IRN / e-invoice
- E-Way
- provider credential/token resolution
- artifact persistence and audit

## Current Active Runtime Path

### Primary runtime models

The active sales compliance flow currently depends on these models:

- `SalesEInvoice`
- `SalesEInvoiceCancel`
- `SalesEWayBill`
- `SalesEWayBillCancel`
- `SalesComplianceActionLog`
- `SalesComplianceExceptionQueue`
- `SalesComplianceErrorCode`
- `SalesMasterGSTCredential`
- `SalesMasterGSTToken`

Relevant files:

- [sales/models/sales_compliance.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_compliance.py)
- [sales/models/mastergst_models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/mastergst_models.py)
- [sales/services/sales_compliance_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/services/sales_compliance_service.py)
- [sales/services/providers/credential_resolver.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/services/providers/credential_resolver.py)

### Runtime behavior summary

1. `SalesMasterGSTCredential`
   - source of active provider credentials
   - scoped by:
     - `entity`
     - `environment`
     - `service_scope`

2. `SalesMasterGSTToken`
   - active token cache for those credentials

3. `SalesEInvoice`
   - current per-invoice e-invoice artifact
   - stores latest IRN state, request/response snapshot, errors, provenance

4. `SalesEWayBill`
   - current per-invoice E-Way artifact
   - should be treated as the practical canonical EWB row

5. `SalesComplianceActionLog`
   - append-only operation history

6. `SalesComplianceExceptionQueue`
   - open statutory/compliance work queue

## Current Compatibility Pattern

### EWB fields duplicated on `SalesEInvoice`

`SalesEInvoice` still keeps:

- `ewb_no`
- `ewb_date`
- `ewb_valid_upto`

This is still in use for compatibility because:

- some IRP responses return EWB details together with IRN
- older read paths historically used e-invoice artifact as a fallback source

Current design decision:

- `SalesEWayBill` is the practical canonical EWB artifact
- `SalesEInvoice` keeps mirrored EWB summary fields for backward compatibility

Status:

- keep for now
- not an immediate removal candidate
- removal should happen only after all read paths and reports stop depending on fallback behavior

## Legacy / Non-Active Models

### 1. `MasterGSTToken`

File:

- [mastergst_models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/mastergst_models.py:184)

Status:

- legacy token cache model
- explicitly documented in code as historical/admin visibility only
- not used by the active provider runtime

Current runtime uses:

- `SalesMasterGSTToken`

Cleanup guidance:

- safe candidate for a later deprecation phase
- do not remove until:
  - admin screens are checked
  - no maintenance scripts depend on it
  - no reporting/debug tooling reads it

### 2. `SalesNICCredential`

File:

- [sales_compliance.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_compliance.py:257)

Status:

- not part of the active WhiteBooks/MasterGST credential path
- current runtime resolves credentials via `SalesMasterGSTCredential`
- appears to reflect an older “generic NIC credential mapping” approach

Important note:

- this is not automatically safe to delete
- it may still be used by:
  - admin forms
  - old migration history assumptions
  - manual support workflows

Cleanup guidance:

- treat as legacy candidate
- before deletion, verify:
  - no admin registrations
  - no forms/serializers/views import it
  - no data entry screen depends on it
  - no DB data is still being maintained by ops users

## Fields That Were Recently Corrected

### `SalesEWayBill.eway_source`

Status before fix:

- field existed but was not reliably populated

Status now:

- stamped during active flows
  - `IRN` for IRN-based E-Way
  - `DIRECT` for B2C direct E-Way

Meaning:

- now trustworthy for downstream reporting and logic

### Provenance fields on artifacts

Both `SalesEInvoice` and `SalesEWayBill` now persist:

- `provider_name`
- `provider_environment`
- `credential_gstin`

Meaning:

- future provider switching is easier to audit
- sandbox/production provenance is visible in artifact rows
- debugging credential mismatch issues is easier

## Cleanup Candidates By Priority

### Low-risk later cleanup candidates

1. `MasterGSTToken`
   - likely removable after confirming no admin/report/debug dependency

2. direct read-side fallback patterns
   - continue moving to helper-based reads
   - eventually read EWB details from `SalesEWayBill` only

### Medium-risk later cleanup candidates

1. `SalesNICCredential`
   - likely legacy, but must be verified carefully

2. mirrored EWB fields on `SalesEInvoice`
   - should remain until all callers stop using them

### Not cleanup candidates right now

Do not target these for removal:

- `SalesMasterGSTCredential`
- `SalesMasterGSTToken`
- `SalesEInvoice`
- `SalesEWayBill`
- `SalesComplianceActionLog`
- `SalesComplianceExceptionQueue`

These are part of the current active compliance runtime.

## Recommended Future Cleanup Sequence

### Phase 1. Inventory

Check all references for:

- `SalesNICCredential`
- `MasterGSTToken`

Include:

- Django admin
- serializers
- views
- cron/jobs/commands
- scripts
- reporting/export code

### Phase 2. Mark Explicitly Legacy

If still present after inventory:

- add stronger docstrings/comments
- remove from broad exports if not needed
- avoid new runtime usage

### Phase 3. Read-Path Simplification

Continue converging toward:

- `SalesEWayBill` = canonical EWB row
- `SalesEInvoice` = canonical IRN row

### Phase 4. Remove Legacy Tables

Only after verification and data review:

- retire `MasterGSTToken`
- consider retiring `SalesNICCredential`
- only later consider dropping mirrored EWB fields from `SalesEInvoice`

## Practical Conclusion

As of now:

- the active compliance model structure is sound
- the provider runtime is using the correct credential/token tables
- the main legacy candidates are:
  - `MasterGSTToken`
  - `SalesNICCredential`

However:

- they should be treated as planned cleanup items, not immediate deletions
- current priority should remain stability of the active sales compliance flow

