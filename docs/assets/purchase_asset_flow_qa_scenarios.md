# Purchase Asset Flow QA Scenarios

Date: 2026-05-09

## Purpose

This checklist is for testing the newly implemented purchase classification and purchase-to-asset flow.

It focuses on:

- product setup
- purchase invoice behavior
- inventory suppression
- expense flow
- asset intake creation
- review queue
- capitalization gate

## Scope

Test these `3` purchase behaviors:

- `inventory`
- `expense`
- `asset`

## Pre-Test Setup

Before testing, make sure you have:

- at least one active entity
- one active subentity / branch
- one financial year
- one vendor ledger
- one inventory product
- one expense product
- one asset product
- one asset category with ledger mapping

Recommended sample products:

- `Resale Monitor` -> inventory
- `Office Food Expense` -> expense
- `Office Computer` -> asset

## Scenario 1: Product Master Saves Inventory Behavior

### Steps

1. Open product master
2. Create or edit a product
3. Set purchase behavior to `inventory`
4. Save

### Expected Result

- product saves successfully
- purchase behavior is visible as `inventory`

## Scenario 2: Product Master Saves Expense Behavior

### Steps

1. Open product master
2. Create or edit a product
3. Set purchase behavior to `expense`
4. Save

### Expected Result

- product saves successfully
- purchase behavior is visible as `expense`

## Scenario 3: Product Master Saves Asset Behavior

### Steps

1. Open product master
2. Create or edit a product
3. Set purchase behavior to `asset`
4. select a default asset category
5. Save

### Expected Result

- product saves successfully
- purchase behavior is visible as `asset`
- default asset category is saved

## Scenario 4: Asset Product Without Asset Category Is Blocked

### Steps

1. Open product master
2. Set purchase behavior to `asset`
3. leave default asset category blank
4. Save

### Expected Result

- save is blocked
- validation clearly asks for default asset category

## Scenario 5: Expense Purchase Does Not Create Inventory Move

### Steps

1. Create a purchase invoice
2. Add an expense-classified product like `Office Food Expense`
3. Save and post

### Expected Result

- purchase invoice posts successfully
- no inventory movement is created for the line
- no asset intake is created

## Scenario 6: Expense Purchase Requires Valid Expense / Purchase Account

### Steps

1. Create a purchase invoice
2. Add an expense line with missing purchase/expense account
3. Try to save

### Expected Result

- save is blocked
- validation clearly asks for purchase or expense account

## Scenario 7: Inventory Purchase Still Creates Inventory Move

### Steps

1. Create a purchase invoice
2. Add an inventory-classified product
3. Save and post

### Expected Result

- purchase invoice posts successfully
- inventory movement is created
- no asset intake is created

## Scenario 8: Asset Purchase Creates CWIP Intake

### Steps

1. Create a purchase invoice
2. Add an asset-classified product like `Office Computer`
3. Save and post

### Expected Result

- purchase invoice posts successfully
- linked asset intake is created
- created asset status is `CAPITAL_WIP`
- purchase document number is stored on the asset

## Scenario 9: Purchase Line Shows Linked Intake

### Steps

1. Open a posted purchase invoice with asset lines
2. Inspect the saved line in the purchase grid

### Expected Result

- linked asset intake is visible on the line
- asset code or intake reference is shown
- line shows intake status such as `CWIP Created`

## Scenario 10: Purchase Screen Shows Linked Intake Count

### Steps

1. Open a posted purchase invoice with asset lines
2. Inspect the purchase header chips / footer chips

### Expected Result

- asset line count is visible
- linked intake count is visible

## Scenario 11: Purchase Drill Opens Asset Review Queue

### Steps

1. Open a posted purchase invoice with asset lines
2. Click `Review Asset Intake`

### Expected Result

- Asset Master opens
- review queue is set to purchase intake
- linked asset is opened directly in workspace

## Scenario 12: Asset Review Queue Shows Purchase Intake Assets

### Steps

1. Open Asset Master
2. Select `Purchase Intake Review`

### Expected Result

- purchase-created intake assets are shown
- normal unrelated assets are not mixed into this filtered review queue

## Scenario 13: Purchase Intake Asset Shows Traceability

### Steps

1. Open a purchase-created intake asset in Asset Master

### Expected Result

- purchase reference is visible
- purchase intake banner is visible
- the user can identify the originating purchase

## Scenario 14: Capitalization Is Blocked When Review Data Is Missing

### Steps

1. Open a purchase-created intake asset
2. Remove or leave blank one or more required review fields:
- location
- custodian
- useful life
- depreciation method
3. Try to capitalize

### Expected Result

- capitalization is blocked
- error clearly tells what is missing

## Scenario 15: Capitalization Works When Review Data Is Complete

### Steps

1. Open a purchase-created intake asset
2. Complete all required review fields
3. Capitalize

### Expected Result

- capitalization succeeds
- status moves out of `CAPITAL_WIP`
- asset becomes active

## Scenario 16: Unpost Purchase Removes Unprogressed Intake

### Steps

1. Create and post a purchase invoice with asset line
2. confirm intake asset exists in `CAPITAL_WIP`
3. unpost purchase before capitalization

### Expected Result

- linked intake is removed or archived as per design
- purchase line linkage is cleared

## Scenario 17: Unpost Is Blocked After Asset Has Progressed

### Steps

1. Create and post a purchase invoice with asset line
2. capitalize linked intake asset
3. try to unpost the purchase invoice

### Expected Result

- unpost is blocked
- error clearly says linked asset has progressed beyond draft/CWIP

## Scenario 18: Non-Product Line Is Treated as Expense Only

### Steps

1. Create a purchase invoice
2. add a line without selecting product
3. provide description and purchase account
4. Save

### Expected Result

- line is accepted as expense flow
- it is not treated as inventory
- it is not treated as asset

## Scenario 19: Service Product Normalizes to Expense

### Steps

1. Open product master for a service item
2. inspect purchase behavior

### Expected Result

- service product behaves as `expense`
- system does not try to route it as inventory or asset

## Scenario 20: Existing Inventory Purchases Are Not Broken

### Steps

1. Create a standard stock purchase with normal inventory products
2. Save and post

### Expected Result

- standard purchase posting still works
- inventory moves are still created
- no unwanted asset intake or expense rerouting happens

## Suggested Test Data Set

Use one each of:

- low-value expense
- stock item
- capital item

Example:

- `Office Food Expense` amount `1,500`
- `Resale Monitor` qty `5`
- `Office Computer` qty `1`

## Final Sign-Off Questions

Before sign-off, confirm:

1. Can users correctly choose inventory vs expense vs asset?
2. Do expense purchases stay out of stock?
3. Do asset purchases create intake automatically?
4. Can users review intake from the purchase flow?
5. Is capitalization blocked until review is complete?
6. Are old inventory purchase flows still working?

## Exit Criteria

This flow is ready for wider rollout when:

- all three behaviors work as designed
- purchase posting stays stable
- asset review queue is usable
- capitalization gating works
- no incorrect inventory moves are created for expense or asset lines
