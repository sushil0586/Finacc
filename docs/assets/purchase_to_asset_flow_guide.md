# Purchase to Asset Flow Guide

Date: 2026-05-09

## Purpose

This guide defines how a purchase should move into the Asset module when the purchased item is meant for internal business use, such as:

- computers
- printers
- furniture
- vehicles
- office equipment

It also explains the current Finacc behavior and the target operating model that should be followed going forward.

## Current System Reality

Today, a normal posted purchase invoice for a non-service product creates:

- purchase accounting entries
- inventory movement for goods lines

It does **not** automatically create a fixed asset.

That means a purchase invoice alone is not enough to make an item appear in the Asset module.

## Example Scenario

Example:

- organization buys a computer for internal use
- item is entered as a normal goods product in Purchase
- purchase invoice is posted

Current result:

- item appears in inventory movement
- item does not appear in Fixed Assets automatically

Why:

- the purchase line is treated as a goods item
- purchase posting routes non-service goods lines to inventory
- there is no automatic purchase-to-asset bridge yet

## Recommended Business Classification

Every purchasable item should belong to one of these three business behaviors:

1. Inventory item
- meant for resale or stock consumption
- should move into inventory

2. Expense item
- meant for immediate use or consumption
- should go directly to expense

3. Asset item
- meant for long-term internal use
- should go into asset intake / capital WIP / fixed asset flow

## Correct Target Flow for Asset Purchases

The recommended future operating model is:

1. Create the purchase invoice
- vendor invoice is entered in Purchase
- line is identified as an asset purchase

2. Post the purchase invoice
- vendor liability is booked
- GST is booked as applicable
- item should not be treated as normal resale inventory

3. Create an asset intake record
- system should create an asset draft or capital WIP record
- purchase document reference should be preserved

4. Review and enrich the asset
- category
- useful life
- depreciation method
- location
- custodian
- serial number
- asset tag
- put-to-use date

5. Capitalize the asset
- asset becomes active in the Asset module
- capitalization accounting is posted

6. Run downstream asset lifecycle
- depreciation
- transfer
- impairment
- disposal

## Recommended Accounting Model

### Option A: Direct capitalization

At purchase posting:

- DR Fixed Asset
- DR Input GST
- CR Vendor

Use this when:

- asset details are fully known at purchase time
- capitalization happens immediately

### Option B: Capital WIP / Asset clearing

At purchase posting:

- DR Capital WIP / Asset Clearing
- DR Input GST
- CR Vendor

At capitalization:

- DR Fixed Asset
- CR Capital WIP / Asset Clearing

Use this when:

- installation is pending
- multiple invoices contribute to one asset
- capitalization needs approval
- asset becomes usable only later

Recommended for Finacc:

- use `Asset Draft / Capital WIP` as the standard model

This fits the existing Asset module better because it already supports:

- `DRAFT`
- `CAPITAL_WIP`
- `ACTIVE`

## Recommended End-to-End Flow in Finacc

### Step 1: Product setup

For items that may be purchased as assets, the product or purchase line should eventually support a procurement behavior flag:

- `inventory`
- `expense`
- `asset`

Until that exists, the business team must identify such purchases manually.

### Step 2: Purchase entry

Create the purchase invoice with:

- vendor
- bill date
- item details
- quantity
- rate
- taxes

The purchase document should still be the commercial source document.

### Step 3: Posting outcome

For target design, asset purchase posting should:

- book vendor and GST properly
- avoid treating the item as resale stock
- create an asset intake reference

### Step 4: Asset intake

The system should create a draft asset record with:

- entity
- subentity
- purchase document number
- acquisition date
- vendor
- quantity
- gross value
- draft status

### Step 5: Asset review

Finance / admin / asset team should fill:

- asset category
- depreciation method
- useful life
- residual value
- location
- custodian
- tag / serial
- ledger if needed

### Step 6: Capitalization

Asset is capitalized after review.

This step should:

- set capitalization date
- set put-to-use date
- set depreciation start date
- post capitalization accounting
- move asset status to `ACTIVE`

## Current Manual Process to Follow Today

Until automation is built, use this manual process:

1. Enter and post the purchase invoice.
2. Do not rely on purchase posting to create the fixed asset.
3. Create the asset manually in the Asset module.
4. Fill:
- asset name
- category
- gross block
- acquisition date
- vendor
- location
- custodian
- purchase document number

5. Capitalize the asset from the Asset module.

## Mapping Example

Example: Office computer purchased for business use

Purchase side:

- Purchase Invoice No: `PI/...`
- Vendor bill posted
- GST booked

Asset side:

- Asset Name: `Desktop Computer - Finance Team`
- Category: `Computers`
- Gross Block: purchase taxable / capitalized amount as per policy
- Purchase Document No: same purchase invoice number
- Status: `DRAFT` -> `ACTIVE`

## What Should Not Happen

For an asset-intended purchase, the system should avoid:

- treating the item as saleable stock by default
- forcing duplicate manual data entry without reference linkage
- losing vendor / invoice traceability
- mixing asset purchases with normal trading inventory reporting

## Required Future Enhancements

To make this seamless, Finacc should eventually support:

1. Product / line level procurement behavior
- inventory
- expense
- asset

2. Purchase-to-asset bridge
- purchase invoice line creates asset draft automatically

3. Purchase reference linkage
- asset should store purchase document and line reference

4. Capital WIP workflow
- pending capitalization queue

5. Optional approval flow
- procurement -> finance review -> capitalization

## Decision Rules

Use these rules operationally:

### If item is for resale
- use inventory flow

### If item is for immediate consumption
- use expense flow

### If item is for long-term internal use
- use asset flow

## Recommended Interim Policy

Until automation is built:

- office-use computers should be treated as asset purchases
- users should manually create corresponding fixed asset records
- purchase invoice number must be captured in the asset record
- asset capitalization should be done from the Asset module only

## UAT Checklist for Future Automation

When purchase-to-asset automation is built, test:

1. Asset-tagged purchase line should not post as normal inventory.
2. Asset draft should be created automatically after purchase posting.
3. Purchase document number should flow into asset reference fields.
4. Capitalization should move draft/CWIP asset to active asset correctly.
5. Depreciation should run only after capitalization.
6. Vendor and GST accounting should remain correct.
7. Partial capitalization and multi-line asset purchases should behave correctly.

## Summary

The correct conceptual flow is:

- Purchase creates the commercial transaction
- Asset intake creates the asset candidate
- Capitalization activates the asset for books and depreciation

In the current system:

- Purchase and Asset are still separate flows
- manual asset creation is required after an asset purchase

That is the correct interim operating model until automated purchase-to-asset integration is implemented.
