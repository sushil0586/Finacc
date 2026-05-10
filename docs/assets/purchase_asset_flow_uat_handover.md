# Purchase Asset Flow UAT Handover

Date: 2026-05-09

## Purpose

This document is the final UAT handover note for the purchase classification, expense routing, and purchase-to-asset flow implemented in Finacc.

Use this as the primary reference when:

- briefing UAT users
- explaining delivered scope
- validating expected behavior
- collecting signoff

It summarizes the full delivered behavior and points testers to the detailed QA scenarios.

## Delivered Scope

The purchase flow now supports `3` business behaviors instead of treating every non-service purchase like inventory.

### Supported purchase behaviors

- `inventory`
- `expense`
- `asset`

### Practical effect

- stock items continue to go to inventory
- direct-consumption items can go to expense
- capital items can create asset intake in `CAPITAL_WIP`

## Business Problem Solved

Previously:

- every non-service goods purchase tended to behave like stock
- office-use asset purchases did not naturally enter the asset lifecycle
- direct expenses like food or admin items could be forced into inventory-like handling

Now:

- inventory purchases remain inventory
- expense purchases stay out of inventory
- asset purchases create linked asset intake records for review and capitalization

## Final Implemented Flow

## 1. Product Master

Product master now supports:

- `purchase_behavior`
- `default_asset_category` when behavior is `asset`

### Expected business use

- resale product -> `inventory`
- direct office/admin consumption -> `expense`
- long-term business use -> `asset`

## 2. Purchase Invoice Entry

Purchase lines now carry and preserve `purchase_behavior`.

### Expected behavior

- the selected product drives the purchase behavior
- the line retains that behavior even if product setup changes later
- the Angular frontend preserves the behavior on create/edit/load/save

## 3. Inventory Routing

Only `inventory` lines create inventory movement.

### Expected behavior

- stock purchase -> inventory move created
- expense purchase -> no inventory move
- asset purchase -> no normal inventory move

## 4. Expense Routing

Expense-classified purchase lines:

- stay out of inventory
- do not create asset intake
- require a valid purchase/expense account

### Examples

- food expense
- pantry purchases
- office admin expense
- repairs
- subscriptions

## 5. Asset Intake Routing

Asset-classified purchase lines now create linked asset intake automatically on posting.

### Created intake behavior

- intake is created as `FixedAsset`
- status starts in `CAPITAL_WIP`
- purchase document reference is stored
- purchase line linkage is stored
- vendor and traceability information is retained

## 6. Purchase-to-Asset Drill

Purchase lines with linked asset intake now expose:

- linked asset id
- linked asset code
- linked asset status

Users can drill from purchase into Asset Master review flow.

## 7. Asset Review Queue

Asset Master now supports a dedicated purchase intake review queue.

### Expected behavior

- purchase-created assets can be filtered separately
- the workspace shows purchase traceability
- the workspace shows review readiness

## 8. Capitalization Protection

Purchase-created intake assets cannot be capitalized until review-critical data is complete.

### Required fields before capitalization

- asset category
- asset ledger
- asset name
- acquisition date
- useful life
- depreciation method
- location
- custodian

## 9. Purchase-Side Visibility

The purchase screen now shows:

- asset line count
- linked intake count
- line-level intake state
- review drill action to Asset Master

## What Changed by Area

## Backend

Implemented:

- purchase behavior on products
- purchase behavior persistence on invoice lines
- expense routing
- asset intake creation in `CAPITAL_WIP`
- purchase line to asset linkage
- purchase intake review queue support
- capitalization readiness blocking

## Angular Frontend

Implemented:

- product master purchase behavior support
- product master asset category selection for asset products
- purchase line behavior preservation
- purchase-to-asset drill
- purchase-side linked intake visibility
- asset review queue support
- purchase intake review banner and readiness cues

## Current User Rule

Use this rule in operations:

- if item is for resale or stock tracking -> `inventory`
- if item is directly consumed -> `expense`
- if item is for long-term business use -> `asset`

## Example Classification

- computer for office use -> `asset`
- office chair -> `asset`
- pantry food -> `expense`
- office stationery -> `expense`
- resale laptop in trading business -> `inventory`
- raw material for inventory/production tracking -> `inventory`

## UAT Preparation Checklist

Before UAT, confirm:

- one entity and subentity are active
- vendor ledger is available
- one product exists for each behavior:
  - inventory
  - expense
  - asset
- asset category exists for asset product
- asset ledger mapping is configured
- testers have access to:
  - product master
  - purchase invoice
  - asset master

## Minimum UAT Scenarios

These are the minimum scenarios that should pass before signoff:

1. Inventory product saves with `inventory` purchase behavior.
2. Expense product saves with `expense` purchase behavior.
3. Asset product saves with `asset` purchase behavior and default asset category.
4. Expense purchase posts without inventory move.
5. Inventory purchase posts with inventory move.
6. Asset purchase posts and creates linked asset intake in `CAPITAL_WIP`.
7. Purchase line shows linked asset intake reference.
8. Purchase drill opens Asset Master purchase review queue.
9. Purchase-created asset shows traceability in Asset Master.
10. Capitalization blocks when review fields are missing.
11. Capitalization succeeds when review fields are complete.
12. Unpost behavior is verified for unprogressed asset intake.

## Signoff Checklist

UAT can be considered complete when all of the following are true:

- product setup works for all `3` behaviors
- purchase invoice behavior matches classification
- inventory moves are created only for inventory lines
- expense purchases stay out of inventory
- asset purchases create linked intake records
- purchase-to-asset drill works
- asset review queue works
- purchase-created assets cannot bypass review
- capitalization works only after required data is completed

## Known Operational Position

At this stage:

- purchase classification is implemented
- expense routing is implemented
- asset intake creation is implemented
- purchase-to-asset review flow is implemented

Further future refinement can still be done for:

- richer dashboards
- bulk capital asset procurement refinements
- advanced mismatch warnings
- deeper accounting automation

These are enhancements, not blockers for current UAT.

## Recommended UAT Pack

Share these documents with UAT users:

1. `purchase_asset_flow_uat_handover.md`
2. `purchase_asset_flow_change_summary.md`
3. `purchase_asset_flow_qa_scenarios.md`
4. `purchase_to_asset_flow_guide.md`
5. `asset_uat_checklist.md`

## Linked Detail Documents

For deeper review, see:

- `purchase_asset_flow_change_summary.md`
- `purchase_asset_flow_qa_scenarios.md`
- `purchase_to_asset_flow_guide.md`
- `purchase_classification_and_asset_flow_phases.md`
- `asset_module_end_to_end_guide.md`

## Final UAT Position

The delivered flow is now suitable for UAT on these business outcomes:

- purchases no longer default blindly to inventory
- direct expenses can be entered correctly
- asset purchases can enter the asset lifecycle from procurement
- purchase and asset teams can work from linked, reviewable intake records

This is the final business-facing handover summary for the current delivered scope.
