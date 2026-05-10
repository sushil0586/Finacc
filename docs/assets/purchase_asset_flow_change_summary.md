# Purchase Asset Flow Change Summary

Date: 2026-05-09

## Purpose

This document summarizes what has been implemented in Finacc for the purchase classification and purchase-to-asset flow.

It is intended for:

- product owners
- QA teams
- implementation consultants
- finance and procurement users

Use it when:

- explaining what changed
- checking current system behavior
- preparing training or UAT
- aligning backend, frontend, and business teams

## Summary

Finacc no longer treats every non-service purchase like inventory by default.

The purchase flow now supports `3` purchase behaviors:

- `inventory`
- `expense`
- `asset`

This means a purchase line can now follow the correct downstream flow instead of always creating stock movement.

## What Changed

## 1. Product Master Now Supports Purchase Behavior

Products now carry an explicit purchase classification:

- `inventory`
- `expense`
- `asset`

### Business effect

- resale or stock items can stay inventory
- office/admin items can be expense
- capital items can become asset intake

## 2. Asset Products Can Carry a Default Asset Category

When a product is marked as `asset`, it can also carry a default asset category.

### Business effect

When such a product is purchased and posted:

- the system knows which asset category to use
- the intake can be created in `Capital WIP`

## 3. Purchase Invoice Lines Persist Purchase Behavior

Purchase lines now carry `purchase_behavior` on the document itself.

### Business effect

Even if product master changes later, the line keeps the behavior used at the time of transaction.

## 4. Inventory Movement Is Now Limited to Inventory Lines

Only purchase lines classified as `inventory` create stock movement.

### Business effect

The following will no longer incorrectly enter stock:

- food expense
- admin purchases
- capital asset purchases

## 5. Expense Purchases Now Stay Out of Inventory

Expense-classified lines:

- do not create inventory movement
- do not create asset intake
- must point to a valid purchase or expense account

### Business effect

This supports direct expense cases like:

- pantry
- refreshments
- repairs
- office admin expense

## 6. Asset Purchases Now Create Asset Intake

When a purchase line is classified as `asset` and the invoice is posted:

- the system creates a linked `FixedAsset` intake record
- status is created as `CAPITAL_WIP`
- purchase document reference is stored
- vendor and cost traceability are stored

### Business effect

A capital purchase now enters the asset pipeline instead of being lost in inventory.

## 7. Purchase Lines Now Link Back to Asset Intake

Purchase invoice lines now expose the linked asset intake details:

- asset intake id
- asset code
- asset status

### Business effect

The purchase screen can show and drill into the created intake.

## 8. Asset Review Queue for Purchase Intake Is Available

Asset Master now supports a purchase review queue.

### Business effect

Users can filter assets to only see purchase-created intake items that still need review or capitalization.

## 9. Purchase Screen Now Shows Linked Intake Visibility

On the purchase invoice UI:

- asset lines are visible as asset-classified lines
- linked intake count is shown
- linked asset intake rows can be opened from purchase into Asset Master

### Business effect

Users can move from purchase to asset review without manually searching.

## 10. Capitalization Is Now Protected by Review Readiness

Purchase-created intake assets cannot be capitalized until critical review data is completed.

### Required review fields

- asset category
- asset ledger
- asset name
- acquisition date
- useful life
- depreciation method
- location
- custodian

### Business effect

Users cannot accidentally capitalize incomplete asset intake records.

## Current End-to-End Flow

## Inventory Purchase

1. Product is marked `inventory`
2. Purchase invoice is created
3. Invoice is posted
4. Inventory movement is created
5. No asset intake is created

## Expense Purchase

1. Product or line is marked `expense`
2. Purchase invoice is created
3. Invoice is posted
4. Expense booking happens
5. No inventory movement is created
6. No asset intake is created

## Asset Purchase

1. Product is marked `asset`
2. Product carries default asset category
3. Purchase invoice is created
4. Invoice is posted
5. Asset intake is auto-created in `CAPITAL_WIP`
6. User opens Asset Master purchase review queue
7. User completes review details
8. User capitalizes the asset

## What Is Already Completed

- purchase behavior foundation
- direct expense purchase routing
- asset intake creation from posted purchase lines
- backend traceability from purchase line to asset
- asset review queue
- purchase-to-asset drill from Angular
- capitalization readiness blocking for purchase intake

## What Is Not Yet a Final Phase

These areas can still be improved further:

- richer purchase-side status messaging
- dashboard summary for pending intake review
- stronger mismatch warnings before posting
- bulk asset purchase refinement
- advanced procurement-to-CWIP accounting controls

## Recommended User Rule

Use this simple rule in operations:

- if item is for resale or stock tracking -> `inventory`
- if item is directly consumed -> `expense`
- if item is for long-term business use -> `asset`

## Example Mapping

- computer for office use -> `asset`
- office chair -> `asset`
- pantry food -> `expense`
- courier bill -> `expense`
- resale laptop in trading business -> `inventory`
- raw material for production -> `inventory`

## Final Implementation Position

The system is now materially better aligned with real business behavior:

- inventory is no longer the only destination
- expense purchase flow is supported
- asset purchases now have a real intake path

This creates the proper bridge from procurement to fixed asset control.
