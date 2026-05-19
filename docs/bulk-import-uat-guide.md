# Bulk Import UAT Guide (User Perspective)

## Purpose
This guide helps users test:
1. Catalog Product Bulk Upload (`validate` + `commit`)
2. Purchase Legacy Import (`create job` + `commit`)

Goal: confirm success cases, error clarity, and partial-failure handling from UI perspective.

## Preconditions
1. Login with a user having required permissions.
2. Select the correct entity in UI.
3. Ensure master data exists for that entity:
   - Category, UOM, Branch, Godown, PriceList, accounts, etc.
4. Keep these files ready:
   - Valid file
   - File with known validation errors
   - File with mixed valid and invalid rows

## Catalog Product Bulk Upload

### 1) Happy Path (Validate + Commit Success)
1. Go to `Catalog > Products > Bulk Import`.
2. Upload a valid template-based file.
3. Click `Validate`.
4. Expected:
   - `can_commit = true`
   - Error count is `0`
5. Click `Commit`.
6. Expected:
   - Commit success message
   - Products created/updated
   - Opening stock rows imported
   - No row-level errors in job detail

Pass criteria:
- Data is visible in product list and related masters.

### 2) Validation Error Clarity
Use a file with intentional errors:
1. Missing `sku`
2. Invalid `launch_date` (example: `2026-13-99`)
3. `openingqty = 0`
4. `openingrate = -1`
5. Invalid `base_uom_code`
6. Invalid `branch_code` or `godown_code`

Expected:
- Validate fails at row level with clear field-specific messages.
- Error rows show exact sheet + row + field.

Pass criteria:
- User can understand and fix the file without backend support.

### 3) Opening Stock Specific Checks
1. Use positive numeric values (`openingqty > 0`, `openingrate >= 0`).
2. Validate and commit.

Expected:
- No false errors for positive numeric values.
- Commit should not fail with opening quantity/rate errors when row values are valid.

## Purchase Legacy Import

### 1) Full Success Commit
1. Go to `Purchase > Legacy Import`.
2. Create an import job using a valid file.
3. Validate/preview rows.
4. Commit.

Expected:
- Success response in UI
- Job status is `COMMITTED`
- Created documents are visible in purchase list

### 2) Partial Commit Behavior
Use a file where some rows are valid and some are invalid (for example, bad original reference for CN/DN).

Expected:
- Commit returns a partial outcome
- Job status is `PARTIAL`
- UI shows warning/error-style message (not pure success)
- Valid rows commit, failed rows remain with row errors

### 3) Full Failure Commit
Use a file where all rows are invalid for commit.

Expected:
- Commit fails clearly
- Job status is `FAILED`
- UI shows error message (not success)
- No documents are created

## Error Export Testing
For failed/partial jobs:
1. Open job details.
2. Export errors file.

Expected:
- Export includes row number, field, message.
- Export content matches UI error summary.

## Regression Checklist
1. Sales legacy import commit still works.
2. Purchase legacy import profile create/list/update works.
3. Bulk template download/export still works.
4. No HTTP 500 errors on validate/commit for valid files.

## Final Sign-off Criteria
Release is accepted only if:
1. Valid files succeed end-to-end.
2. Invalid files fail with clear actionable errors.
3. Partial commit is clearly reported as partial (not full success).
4. Failed commit is clearly reported as failed.
5. Error export and job detail are consistent with UI messages.

