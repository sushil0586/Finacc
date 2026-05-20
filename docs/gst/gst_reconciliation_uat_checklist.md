# GST Reconciliation UAT Checklist

## Scope
Use this checklist for controlled internal testing of the new `/gst-reconciliation` workspace and APIs.

## Preconditions
- User has `gst.reconciliation.view`
- Reviewer user has `gst.reconciliation.review`
- Run owner or admin has `gst.reconciliation.manage`
- Feature `feature_financial` is enabled for the entity
- Entity and FY context are selected correctly
- Demo data is loaded with:
  - `python manage.py seed_gst_reconciliation_demo --entity <id> --entityfinid <id> --user <id>`

## Scenarios

### 1. Menu and Route Access
- Confirm GST Reconciliation menu is visible only for users with `gst.reconciliation.view`
- Confirm direct `/gst-reconciliation` route redirects unauthorized users to the friendly unauthorized screen
- Confirm the old purchase statutory workspace still opens normally

### 2. GSTR-2B Import
- Import a valid GSTR-2B JSON file
- Import a valid GSTR-2B Excel file
- Confirm imported return is created
- Confirm reconciliation run is created when requested
- Confirm imported rows are visible and read-only

### 3. Auto Match
- Run matching on a newly imported run
- Confirm run status changes to review-ready state
- Confirm matched, mismatched, and missing cases are reflected in item grid
- Confirm dashboard counts update

### 4. Manual Match
- Open one mismatched item
- Search source documents by:
  - invoice number
  - GSTIN
  - party name
- Preview a candidate document
- Manually match the item
- Confirm:
  - item status changes
  - action log is created
  - next-item navigation works

### 5. Manual Unmatch
- Unmatch a manually linked item
- Confirm item returns to pending review
- Confirm audit log is created

### 6. Ignore
- Ignore an item with a required note
- Confirm item becomes ignored
- Confirm ignored count changes in summary
- Confirm item cannot be ignored without a note

### 7. Accept Mismatch
- Accept mismatch on a mismatched item with note
- Confirm accepted mismatch count changes in summary
- Confirm action log captures note and user

### 8. Bulk Actions
- Bulk assign items to reviewer
- Bulk ignore items
- Bulk reopen items
- Bulk accept mismatch
- Bulk mark reviewed
- Bulk unmatch
- Confirm response shows:
  - success count
  - failed count
  - per-item errors for invalid items

### 9. Reviewer Assignment
- Assign item to another reviewer
- Use assign-to-me shortcut
- Confirm users without review permission do not see review actions
- Confirm assigned reviewer restrictions work on non-admin users

### 10. Source Document Search
- Search without item context using entity + FY
- Search from item context
- Confirm cross-entity and wrong-scope documents do not appear
- Confirm incompatible GSTIN/period candidates are rejected at manual match time

### 11. Supplier Analytics
- Open Supplier Analytics tab
- Verify:
  - GSTIN
  - supplier name
  - total items
  - mismatched items
  - missing in books
  - unresolved count
  - taxable/tax at risk

### 12. Dashboard Counts
- Verify run summary cards
- Verify queue shortcut counts
- Verify run health/progress bars

### 13. Permission Restrictions
- User with no GST reconciliation permission:
  - cannot see menu
  - cannot open route
- User with view only:
  - can open dashboard and item detail
  - cannot see review/bulk actions
- User with review only:
  - can review items in allowed entity
  - cannot import or close runs
- User with manage:
  - can import, match, and close

### 14. Closed Run Behavior
- Close a run
- Confirm:
  - no manual match
  - no unmatch
  - no ignore
  - no accept mismatch
  - no note edits
  - no bulk mutation actions
- Confirm read-only view still works

### 15. Cross-Entity Safety
- Attempt to access another entity's run ID directly
- Attempt item detail from another entity
- Attempt source-document preview with another entity scope
- Confirm permission denied or not found behavior is safe

## Exit Criteria
- All scenarios pass in one controlled entity
- Backend tests pass
- Angular typecheck passes
- Focused GST reconciliation component specs pass
- No regression in old purchase statutory and GST reports
