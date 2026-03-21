# Financial Legacy Column Drop Plan

This plan is for the final DB cleanup after runtime cutover to normalized profiles.

## Preconditions
- Runtime cutover complete (done): normalized profile tables are source of truth.
- Test + stage validation complete (done).
- `python manage.py audit_legacy_account_columns` shows expected/acceptable usage.

## New Audit Command
- Global: `python manage.py audit_legacy_account_columns`
- Per entity: `python manage.py audit_legacy_account_columns --entity-id <id>`

Target before physical drop:
- All listed legacy columns should be 0 (or explicitly accepted and migrated).

## Legacy Columns Planned for Drop (`financial.account`)

### Compliance (moved to `AccountComplianceProfile`)
- `gstno`, `pan`, `gstintype`, `gstregtype`, `is_sez`
- `cin`, `msme`, `gsttdsno`
- `tdsno`, `tdsrate`, `tdssection`, `tds_threshold`
- `istcsapplicable`, `tcscode`

### Commercial (moved to `AccountCommercialProfile`)
- `partytype`, `creditlimit`, `creditdays`, `paymentterms`
- `currency`, `blockstatus`, `blockedreason`
- `approved`, `agent`, `reminders`

### Address (moved to `AccountAddress`)
- `address1`, `address2`, `addressfloorno`, `addressstreet`, `pincode`
- `country_id`, `state_id`, `district_id`, `city_id`

## Migration Sequence (recommended)

### Phase A: Schema decouple
1. Remove model-level references in `financial/models.py`:
   - `LEGACY_PROFILE_FIELDS`
   - `_assert_no_new_legacy_profile_writes` and related `save()` guard
2. Remove constraints/indexes referencing legacy columns:
   - `uq_account_entity_gstno_present`
   - `ck_account_creditdays_nonneg`
   - `ck_account_creditlimit_nonneg`
   - `ix_account_entity_gstno`

### Phase B: Physical drop migration
3. Create migration to remove fields from `financial.account` listed above.
4. Keep normalized profile models unchanged.

### Phase C: Verify
5. Run:
   - `python manage.py check`
   - financial + reports focused tests
6. Smoke test account create/update, dropdowns, reports, posting flows.

## Rollback Strategy
- If rollback is needed during deploy window:
  - rollback app to pre-drop release
  - restore DB snapshot taken before Phase B

## Notes
- Historical migrations remain unchanged.
- Keep this as a dedicated release to simplify incident handling.
