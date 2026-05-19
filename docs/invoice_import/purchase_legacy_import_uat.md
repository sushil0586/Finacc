# Purchase Legacy Import UAT Guide

## Purpose
This guide covers UAT for the current purchase legacy import workflow, including:
- purchase template download
- upload and validation
- manual review
- credit/debit note validation
- purchase import policy controls
- RBAC split between uploader, reviewer, and poster

## Roles To Prepare
Create or identify these users before testing:
- `Uploader`: has purchase legacy import `create`
- `Reviewer`: has purchase legacy import `update`
- `Poster`: has purchase legacy import `post`
- `Viewer`: has purchase legacy import `view`

Recommended UAT setup:
- one entity with at least one branch/subentity
- one vendor with GST details
- one valid purchase invoice sample
- one valid purchase credit note sample
- one intentionally invalid purchase credit note sample

## Master Data Preconditions
Before testing, ensure the target entity has:
- vendor account
- GST-ready purchase context
- required purchase accounts or products for `header_plus_lines`
- financial year and branch selection available in UI

## Files To Keep Ready
- valid header-only purchase invoice file
- valid header-plus-lines purchase invoice file
- purchase note file with correct `original_source_key`
- purchase note file with vendor mismatch
- purchase note file with earlier date than original
- purchase note file with outstanding exceeding original
- purchase note file with small amount variance

## UAT 1: Template Download
### Objective
Confirm the purchase template includes the current columns needed for realistic imports.

### Steps
1. Login as a user with purchase legacy import `view`.
2. Open Purchase Legacy Import.
3. Download the purchase template in:
   - `outstanding_only + header_only`
   - `full_history + header_plus_lines`
4. Inspect the downloaded file.

### Expected Result
- Template downloads successfully.
- Purchase template contains:
  - `total_discount`
  - `tds_amount`
  - `gst_tds_amount`
  - `original_source_key`
  - line-level discount and tax columns in `header_plus_lines`

## UAT 2: Happy Path Purchase Invoice Import
### Objective
Confirm a valid purchase invoice imports end to end.

### Steps
1. Login as `Uploader`.
2. Upload a valid purchase file.
3. Click `Validate Upload`.
4. Open document review summary.
5. If review is required, login as `Reviewer` and mark the job reviewed.
6. Login as `Poster` and commit the job.

### Expected Result
- Job validates successfully.
- Document review row shows `Ready`.
- Commit succeeds.
- Imported purchase invoice is visible in purchase list.

## UAT 3: Purchase Header-Plus-Lines Reconciliation
### Objective
Confirm line totals are reconciled against purchase header totals.

### Steps
1. Use `full_history + header_plus_lines`.
2. Upload a file where line taxable or tax totals do not match header values.
3. Validate the upload.

### Expected Result
- Validation fails.
- Grouped purchase document is blocked.
- Row/document issues show which header amount mismatched line totals.

## UAT 4: Manual Review Required
### Objective
Confirm review gating works when enabled in purchase settings.

### Precondition
Set `legacy_import_review_required = on`.

### Steps
1. Login as `Uploader`.
2. Upload a valid purchase file.
3. Validate successfully.
4. Attempt commit without review.

### Expected Result
- Commit is blocked.
- UI instructs the user to review the job before commit.

### Follow-up
1. Login as `Reviewer`.
2. Mark the job reviewed with a review note.
3. Login as `Poster`.
4. Commit the job.

### Expected Result
- Review action succeeds.
- Commit succeeds only after review is completed.

## UAT 5: Purchase Credit Note Happy Path
### Objective
Confirm a valid purchase credit note referencing an original invoice is accepted.

### Steps
1. Import or prepare the original purchase invoice.
2. Upload a purchase credit note file with:
   - valid `original_source_key`
   - same vendor
   - note values lower than or equal to original
3. Validate the upload.

### Expected Result
- Validation succeeds.
- Document review shows original invoice context.
- Review preview is meaningful.

## UAT 6: Purchase Credit Note Vendor Mismatch
### Objective
Confirm vendor mismatch is blocking.

### Steps
1. Use a purchase note pointing to a real original invoice.
2. Change the vendor so it does not match the original.
3. Validate the upload.

### Expected Result
- Validation fails.
- Review preview starts with `Original mismatch`.
- Document issues clearly explain vendor mismatch.

## UAT 7: Purchase Credit Note Earlier Date Rule
### Objective
Confirm date anomaly policy works across `warn` and `hard`.

### Scenario A
Set `legacy_import_note_date_rule = warn`.

### Steps
1. Upload a note with `bill_date` earlier than the original invoice.
2. Validate.

### Expected Result
- Job remains valid if no other blocking issue exists.
- Review preview starts with `Date warning`.

### Scenario B
Set `legacy_import_note_date_rule = hard`.

### Steps
1. Revalidate the same file.

### Expected Result
- Validation fails.
- Review preview starts with `Date issue`.
- Document issues contain `bill_date` error.

## UAT 8: Purchase Credit Note Outstanding Rule
### Objective
Confirm outstanding exceedance policy works across `warn` and `hard`.

### Scenario A
Set `legacy_import_note_outstanding_rule = warn`.

### Steps
1. Upload a note where note outstanding exceeds original outstanding.
2. Validate.

### Expected Result
- Job can still validate if there is no other blocking issue.
- Review preview starts with `Outstanding warning`.

### Scenario B
Set `legacy_import_note_outstanding_rule = hard`.

### Steps
1. Revalidate the same file.

### Expected Result
- Validation fails.
- Review preview starts with `Outstanding issue`.
- Document issues contain `outstanding_amount` error.

## UAT 9: Purchase Note Amount Tolerance
### Objective
Confirm small amount variance can be allowed through configuration.

### Scenario A
Set `legacy_import_note_amount_tolerance = 0.00`.

### Steps
1. Upload a note where taxable total or grand total exceeds original by a small amount.
2. Validate.

### Expected Result
- Validation fails for amount exceedance.

### Scenario B
Set `legacy_import_note_amount_tolerance = 10.00`.

### Steps
1. Revalidate the same file where the variance is within `10.00`.

### Expected Result
- Validation succeeds if no other blocking issue exists.

## UAT 10: Review Screen Usability
### Objective
Confirm grouped review is usable for operators.

### Steps
1. Upload a file with a mix of:
   - normal purchase invoices
   - purchase notes
   - blocked rows
   - warning-only rows
2. Use review filters:
   - `Blocked`
   - `Needs Review`
   - `Ready`
   - `Notes only`
3. Expand document-level issues.

### Expected Result
- Filters work correctly.
- Review badges and preview chips match issue type.
- Expanded document issues show all grouped errors/warnings clearly.

## UAT 11: RBAC Split
### Objective
Confirm different users can only perform permitted actions.

### Scenario A: Viewer
Expected:
- can download template
- can open job detail
- can view reconciliation
- cannot upload
- cannot review
- cannot commit

### Scenario B: Uploader
Expected:
- can upload and validate
- can create profiles if allowed by business policy
- cannot review unless `update` is also granted
- cannot commit unless `post` is also granted

### Scenario C: Reviewer
Expected:
- can open validated job
- can mark reviewed
- cannot commit unless `post` is also granted

### Scenario D: Poster
Expected:
- can commit validated and reviewed job
- should not need create permission to commit an already-created job

## UAT 12: Error Export
### Objective
Confirm error export matches review and validation output.

### Steps
1. Validate a file with known failures.
2. Download error CSV and XLSX.
3. Compare exported issues with on-screen errors.

### Expected Result
- Exports contain row number, field, and message.
- Exported issues match UI issues.

## Sign-off Checklist
Mark release ready only if all of these pass:
- template includes the required purchase fields
- valid purchase invoice imports successfully
- manual review gate works when enabled
- purchase note vendor mismatch is blocked
- purchase note date rule works for `warn` and `hard`
- purchase note outstanding rule works for `warn` and `hard`
- purchase note amount tolerance works as configured
- document review filters and issue expansion work
- RBAC split works for `view`, `create`, `update`, and `post`
- error export matches validation output

## Suggested Local Backend Commands
Run these before final sign-off in the project `venv`:

```bash
python manage.py test invoice_import.tests --keepdb
python manage.py test purchase.tests --keepdb
```
