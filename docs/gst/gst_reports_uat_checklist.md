# GST Reports UAT Checklist

Date: 2026-05-08

## Purpose

Use this checklist to validate GST Reports before rollout or signoff.

This checklist is designed for:
- QA teams
- finance testers
- implementation teams
- project owners reviewing report readiness

## Testing Scope

This UAT covers:
- access
- filter behavior
- summary loading
- section or table drilldown
- validation behavior
- export behavior
- annual and monthly reporting sanity

## Pre-UAT Conditions

Before testing, confirm:

- users exist and can log in
- entity access is assigned
- the target financial year exists
- branch or subentity data exists if branch filtering is used
- sample posted sales and purchase transactions exist
- GST-related source data is meaningful enough to produce report values

## UAT Section 1: Access Validation

### Test 1. GSTR-1 access

Steps:
1. Log in as an authorized user.
2. Open `gstreport`.

Expected result:
- the screen opens
- no unauthorized message appears

### Test 2. GSTR-3B access

Steps:
1. Log in as an authorized user.
2. Open `gstr3breport`.

Expected result:
- the screen opens
- report loads for a valid scope

### Test 3. GSTR-9 access

Steps:
1. Log in as an authorized user.
2. Open `gstr9report`.

Expected result:
- the screen opens
- meta and summary can load

### Test 4. Unauthorized access denial

Steps:
1. Log in as a user without GST report access.
2. Try to open GST report screens.

Expected result:
- access is denied cleanly

## UAT Section 2: Filter and Scope Validation

### Test 5. Entity filter behavior

Steps:
1. Open each GST report.
2. Select the intended entity.

Expected result:
- data loads only for the selected entity

### Test 6. Financial year and period behavior

Steps:
1. Change the period or year.
2. Reload the report.

Expected result:
- report changes according to the selected period

### Test 7. Subentity or branch scope

Steps:
1. Use a branch-specific scope if available.
2. Compare with all-branch scope if business data allows.

Expected result:
- values respect the branch scope

## UAT Section 3: GSTR-1 Functional Validation

### Test 8. GSTR-1 summary loads

Expected result:
- summary appears without error
- key section totals are visible

### Test 9. GSTR-1 section drilldown works

Steps:
1. Open one or more sections such as B2B, B2CL, exports, or notes.

Expected result:
- section grid opens
- values align with the summary

### Test 10. GSTR-1 invoice drilldown works

Expected result:
- invoice detail opens for a valid row

### Test 11. GSTR-1 validations return warnings when expected

Expected result:
- warning list loads cleanly
- known sample issues appear where applicable

### Test 12. GSTR-1 export works

Expected result:
- export is generated
- exported values reasonably match on-screen filters

## UAT Section 4: GSTR-3B Functional Validation

### Test 13. GSTR-3B summary loads

Expected result:
- report loads without error
- tax and ITC summary values appear

### Test 14. GSTR-3B totals are reasonable

Expected result:
- values broadly align with source period expectations
- no obvious negative or blank anomalies without business reason

### Test 15. GSTR-3B export works

Expected result:
- export completes
- exported values match on-screen scope

## UAT Section 5: GSTR-9 Functional Validation

### Test 16. GSTR-9 meta loads

Expected result:
- meta payload loads
- table list and endpoints are available

### Test 17. GSTR-9 summary loads

Expected result:
- summary loads without error
- table statuses are visible

### Test 18. GSTR-9 table drilldown works

Expected result:
- tables load correctly
- values align with annual expectations

### Test 19. GSTR-9 validations work

Expected result:
- validation payload loads
- warning count behaves correctly

### Test 20. GSTR-9 export works

Expected result:
- JSON, CSV, or XLSX export works as expected

### Test 21. GSTR-9 freeze workflow works

If used in your rollout:

Expected result:
- freeze can be created
- latest freeze can be fetched
- history shows multiple versions when applicable

## UAT Section 6: Cross-Checks

### Test 22. Report vs source transaction sample check

Steps:
1. Pick a small set of known invoices.
2. Compare source values with report output.

Expected result:
- report values reflect the posted source data correctly

### Test 23. Report vs export sample check

Steps:
1. Review totals on screen.
2. Export with the same filters.

Expected result:
- exported data matches the screen scope and totals

## UAT Signoff Fields

Record:
- test date
- tester name
- entity tested
- financial year tested
- branch or subentity tested
- pass/fail status
- issues found
- final signoff owner

## Exit Criteria

GST Reports can be treated as UAT-ready when:

- authorized users can access the correct screens
- unauthorized users are blocked
- summary and detail screens load cleanly
- validations behave correctly
- exports work
- sample totals match source transactions
- no major access or data integrity issue remains open
