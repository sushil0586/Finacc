# Asset Module UAT Checklist

## Purpose

This document helps business users, finance users, QA teams, and implementation teams test the Asset module end to end.

It is written in simple language so non-technical users can use it during UAT.

This checklist covers:

- setup validation
- screen access validation
- transaction flow validation
- report validation
- accounting validation
- negative scenario validation

---

## How To Use This Checklist

Recommended approach:

1. complete setup checks first
2. test master data screens
3. test lifecycle actions
4. test depreciation flow
5. test reports
6. test role and permission behavior
7. record evidence and sign-off

For every test case, mark:

- `Pass`
- `Fail`
- `Blocked`
- `Not Applicable`

Also capture:

- tester name
- test date
- entity used
- subentity used if applicable
- screenshots or report evidence

---

## UAT Scope

Main screens covered:

- `Asset Settings`
- `Asset Category Master`
- `Asset Master`
- `Depreciation Run`
- `Fixed Asset Register`
- `Depreciation Schedule`
- `Asset Events`
- `Asset History`

---

## Section 1. Setup Readiness

### 1.1 Feature and access

- Verify the Asset feature is enabled for the test tenant.
- Verify admin user can open all asset screens.
- Verify finance user can open the required operational screens.
- Verify users without asset permission cannot access restricted screens.

Expected result:

- authorized users can access the correct pages
- unauthorized users are blocked

### 1.2 Base setup

- Verify at least one financial year is available for testing.
- Verify required ledgers exist in the chart of accounts.
- Verify required subentities exist if subentity testing is in scope.
- Verify asset numbering policy is decided.
- Verify depreciation method policy is decided.

Expected result:

- testers are not blocked by missing master setup

---

## Section 2. Asset Settings

### 2.1 Screen open

- Open `Asset Settings`.
- Change scope between global and subentity if applicable.

Expected result:

- screen loads without error
- scope can be changed

### 2.2 Save defaults

- Set default asset document code.
- Set default disposal document code.
- Set default depreciation method.
- Set useful life months and residual value.
- Save the settings.

Expected result:

- settings save successfully
- reopening the screen shows saved values

### 2.3 Policy controls

- Test capitalization basis values.
- Test depreciation posting mode.
- Test depreciation lock rule.
- Test backdated capitalization rule.
- Test negative NBV rule.
- Test auto-number assets toggle.
- Test require asset tag toggle.

Expected result:

- values save correctly
- related operational screens reflect the policy behavior

---

## Section 3. Asset Category Master

### 3.1 Create category

- Create a new asset category.
- Enter code and name.
- Select nature.
- Select depreciation method.
- Enter useful life and residual value.

Expected result:

- category saves successfully

### 3.2 Ledger mapping

- Assign asset ledger.
- Assign accumulated depreciation ledger.
- Assign depreciation expense ledger.
- Assign impairment ledgers if impairment is enabled.
- Assign gain and loss on sale ledgers.

Expected result:

- category saves successfully
- ledgers remain visible on reopen

### 3.3 Validation

- Try saving category without mandatory fields.
- Try creating duplicate category code in same scope.

Expected result:

- proper validation message appears
- duplicate creation is blocked

---

## Section 4. Asset Master

### 4.1 Create asset manually

- Open `Asset Master`.
- Click `New Asset`.
- Select category.
- Select ledger.
- enter asset code if auto-number is off
- enter asset name
- enter acquisition date
- enter gross block
- enter useful life and depreciation details if needed
- save the asset

Expected result:

- asset is created successfully
- asset appears in the asset grid

### 4.2 Auto numbering

- If auto-numbering is enabled, create a new asset without entering asset code.

Expected result:

- system generates asset code automatically

### 4.3 Require asset tag

- If asset tag is required, try saving or posting without asset tag.

Expected result:

- system follows configured rule

### 4.4 Edit asset

- Open an existing draft asset.
- update non-financial fields such as location, department, or custodian
- save changes

Expected result:

- changes save successfully

### 4.5 Bulk import

- download or prepare bulk import file
- validate the file
- commit the import

Expected result:

- validation errors are shown clearly if data is wrong
- valid records import once only
- repeated commit does not duplicate import

---

## Section 5. Capitalization

### 5.1 Capitalize draft asset

- Select a draft asset.
- choose `Capitalize`
- enter capitalization date
- choose counter ledger
- submit

Expected result:

- asset status becomes active
- capitalization date is stored
- posting is created

### 5.2 Threshold rule

- Create an asset below threshold if threshold rule is active.
- try capitalization

Expected result:

- system follows the configured threshold behavior
- warning or blocking should match policy

### 5.3 Backdated capitalization rule

- try capitalization on a backdated date

Expected result:

- system follows the configured backdated rule

---

## Section 6. Depreciation Run

### 6.1 Create run

- Open `Depreciation Run`
- create a run with:
  - financial year
  - subentity if needed
  - run code
  - period from
  - period to
  - posting date

Expected result:

- run is created successfully

### 6.2 Calculate run

- calculate the run

Expected result:

- run moves to calculated status
- line items appear
- total asset count is shown
- total depreciation amount is shown

### 6.3 Post run

- post the calculated run

Expected result:

- run moves to posted status
- posting batch is created
- asset accumulated depreciation updates
- net book value updates

### 6.4 Cancel run

- cancel a calculated run
- cancel a posted run if policy and scenario allow

Expected result:

- run moves to cancelled status
- if previously posted, accounting evidence remains auditable
- asset balances reverse correctly

### 6.5 Locked period rule

- try depreciation posting in locked period

Expected result:

- system follows the configured lock rule

---

## Section 7. Impairment

### 7.1 Impair active asset

- open an active asset
- choose `Impair`
- enter impairment amount
- enter posting date
- save

Expected result:

- impairment amount updates
- net book value reduces
- impairment posting is created

### 7.2 Validation

- try impairment amount greater than current net book value

Expected result:

- system blocks the transaction

---

## Section 8. Transfer

### 8.1 Transfer asset

- open an asset
- choose `Transfer`
- change subentity, location, department, or custodian
- save

Expected result:

- operational details update successfully

### 8.2 Scope check

- transfer to an invalid or inactive subentity

Expected result:

- system blocks invalid scope movement

---

## Section 9. Disposal

### 9.1 Dispose active asset

- open an active asset
- choose `Dispose`
- enter disposal date
- enter sale proceeds
- choose proceeds ledger
- save

Expected result:

- asset status becomes disposed
- disposal posting is created
- net book value becomes zero
- gain or loss is recorded correctly

### 9.2 Gain and loss scenarios

- test one disposal with gain
- test one disposal with loss

Expected result:

- correct ledger impact is created in each scenario

### 9.3 Backdated disposal rule

- try disposal with backdated date

Expected result:

- system follows policy rule

---

## Section 10. Reports

### 10.1 Fixed Asset Register

- open `Fixed Asset Register`
- filter by financial year
- filter by subentity
- filter by category
- filter by status
- search by asset

Expected result:

- report loads correctly
- totals appear correctly
- pagination works
- export works

### 10.2 Depreciation Schedule

- open `Depreciation Schedule`
- filter by date range and asset

Expected result:

- rows show correct depreciation movement
- pagination works
- export works

### 10.3 Asset Events

- open `Asset Events`
- filter by event type
- filter by date range

Expected result:

- capitalization, depreciation, impairment, and disposal events appear correctly
- pagination works
- export works

### 10.4 Asset History

- open history from asset grid or reports

Expected result:

- full event story appears for the selected asset
- journal lines appear where applicable

---

## Section 11. Accounting Validation

Finance should verify actual postings for:

- capitalization
- depreciation
- impairment
- disposal

Checklist:

- correct ledgers are used
- debit and credit sides are correct
- amounts match expected values
- voucher numbers are traceable
- posting dates are correct
- reversal or cancellation logic is auditable

---

## Section 12. Negative Scenarios

Test these negative scenarios:

- save asset without category
- save asset without ledger
- save asset without asset code when auto-numbering is off
- capitalize asset with zero gross block
- capitalize asset twice
- post depreciation run without calculation
- recalculate posted run
- impair disposed asset
- dispose non-active asset
- create duplicate category code

Expected result:

- user receives clear validation message
- invalid transaction is blocked

---

## Section 13. Role And Permission Checks

Test with at least:

- admin user
- finance user
- restricted user

Validate:

- admin can access all asset pages
- finance user can access operational pages and reports as approved
- restricted user cannot access unauthorized screens

Important routes to test:

- `assetcategorymaster`
- `assetmaster`
- `depreciationrun`
- `assetsettings`
- `fixedassetregister`
- `depreciationschedule`
- `assetevents`
- `assethistory`

Also test legacy-compatible routes if needed:

- `asset-category-master`
- `asset-master`
- `depreciation-run`
- `asset-settings`
- `fixed-asset-register`
- `depreciation-schedule`
- `asset-events`
- `asset-history`

---

## Section 14. UAT Sign-Off Questions

Before sign-off, confirm:

- are business users comfortable with the screen flow?
- are finance users satisfied with accounting output?
- are reports matching expectations?
- are policy rules working as approved?
- are role and permission checks working?
- is opening data migration accepted?
- are exports usable for audit and review?

---

## Suggested Evidence To Attach

- screenshot of saved asset settings
- screenshot of category ledger mapping
- screenshot of created asset
- screenshot of capitalization result
- screenshot of depreciation run posted
- screenshot of impairment result
- screenshot of disposal result
- report exports
- journal posting evidence

---

## Final UAT Summary Template

Use this summary at the end:

- Test cycle: `__________`
- Entity: `__________`
- Subentity: `__________`
- Tester names: `__________`
- Total scenarios tested: `__________`
- Passed: `__________`
- Failed: `__________`
- Blocked: `__________`
- Major open issues: `__________`
- Recommended for go-live: `Yes / No`

---

## Layman Summary

If someone wants the UAT goal explained in one minute:

- first confirm setup
- then create categories and assets
- then test capitalization, depreciation, impairment, transfer, and disposal
- then confirm reports and accounting
- then confirm permissions

In short:

- UAT is complete only when both business flow and accounting flow are proven correct

