# Purchase Classification and Asset Flow Phases

Date: 2026-05-09

## Purpose

This document breaks the purchase-to-asset and purchase-to-expense design into practical implementation phases.

It is intended to help Finacc evolve from the current behavior:

- most non-service purchase lines behave like inventory goods

to a cleaner business model where each purchase line can be treated correctly as:

- inventory
- expense
- asset

## Why This Is Needed

Today, a posted purchase invoice for a non-service product generally creates inventory movement.

That creates a gap for cases like:

- buying a computer for office use
- buying furniture for the company
- buying pantry food for staff
- buying office maintenance material

These are not all inventory purchases.

The system needs a clear classification model so purchase lines can go to the correct downstream flow.

## Target Business Rule

Each purchase line should belong to exactly one of these behaviors:

### 1. Inventory

Use when the item is:

- meant for resale
- meant for stock tracking
- meant for quantity-based warehouse control

Expected outcome:

- inventory move is created
- stock ledger is updated
- no asset record is created

### 2. Expense

Use when the item or service is:

- immediately consumed
- not meant for resale
- not meant to become a capital asset

Examples:

- food expense
- tea / snacks
- courier
- repairs
- internet bill
- housekeeping
- stationery

Expected outcome:

- direct expense posting
- no inventory move
- no asset record

### 3. Asset

Use when the purchase is:

- for long-term internal use
- capital in nature
- expected to enter the fixed asset lifecycle

Examples:

- desktop computer
- laptop
- office chair
- printer
- machine
- vehicle

Expected outcome:

- purchase is linked into asset intake
- no normal trading inventory treatment
- later capitalization into fixed asset register

## Phase Plan

## Phase 1: Purchase Classification Foundation

### Goal

Introduce a formal purchase behavior classification.

### Business Outcome

Every purchased line can be routed correctly.

### Required Design

At product level, introduce:

- `inventory`
- `expense`
- `asset`

Optionally allow line-level override later.

### Rules

- inventory -> inventory flow
- expense -> expense flow
- asset -> asset intake flow

### Notes

This is the foundation phase. Without it, the rest of the design will stay ambiguous.

## Phase 2: Direct Expense Purchase Flow

### Goal

Support non-trading purchases cleanly.

### Typical Use Cases

- food expense
- pantry expense
- office refreshment
- repairs and maintenance
- telephone / internet
- travel / local conveyance

### Expected Flow

1. Create purchase invoice
2. Mark line as `expense`
3. Post purchase invoice
4. System books:
- expense ledger
- GST if applicable
- vendor liability

### Should Not Happen

- no inventory move
- no asset draft

### Example

If the company buys food for staff:

- product/line classification = `expense`
- posting should go to `Staff Welfare`, `Refreshment`, or chosen expense ledger

## Phase 3: Asset Intake Flow

### Goal

Route capital purchases into a controlled asset pipeline.

### Typical Use Cases

- computers
- furniture
- office equipment
- machinery
- electrical fittings above threshold

### Expected Flow

1. Create purchase invoice
2. Mark line as `asset`
3. Post purchase invoice
4. System creates:
- asset draft
or
- capital WIP record

### Data That Should Flow

- purchase document number
- purchase date
- vendor
- quantity
- taxable / capitalizable amount
- branch / subentity
- product description

### Recommended Status

- `DRAFT`
or
- `CAPITAL_WIP`

## Phase 4: Asset Review and Capitalization

### Goal

Complete the fixed asset setup after procurement.

### Asset Review Fields

- asset category
- asset code
- useful life
- depreciation method
- residual value
- location
- custodian
- asset tag
- serial number
- put-to-use date
- capitalization date

### Expected Flow

1. Asset team reviews draft
2. Business validates details
3. Finance capitalizes asset
4. Asset becomes `ACTIVE`
5. Depreciation lifecycle begins

## Phase 5: Controls and Automation

### Goal

Reduce classification mistakes and improve discipline.

### Recommended Controls

- warning if an asset-like item is marked inventory
- warning if a low-value item is marked asset below threshold
- warning if expense item is pushed into inventory
- review dashboard for uncapitalized asset drafts
- mandatory purchase reference for asset drafts

### Reporting Opportunities

- asset intake pending capitalization
- expense purchases by category
- asset purchases by vendor
- inventory vs expense vs asset purchase split

## Food Expense Scenario

## Business Understanding

If your business is **not trading in food**, then food should not go to inventory.

It should be booked as an expense.

## Correct Treatment

Food purchases should usually be classified as:

- `expense`

not:

- `inventory`
- `asset`

## Example Entry Types

Use cases:

- staff lunch
- tea and snacks
- pantry refills

Expected result:

- DR Food / Staff Welfare / Refreshment Expense
- DR GST input if eligible
- CR Vendor

No stock.
No asset.

## Recommended Data Entry Options

### Option A: Expense product

Create repeat-use products such as:

- Office Food Expense
- Pantry Expense
- Refreshment Expense

Mark them as:

- purchase classification = `expense`

### Option B: Direct expense ledger line

For ad hoc purchases, allow purchase line entry directly against an expense account.

This is useful where:

- no inventory tracking is needed
- no reusable product master is needed

## Asset Purchase Scenario

For a computer bought for office use:

- classification = `asset`

Expected result:

1. purchase invoice is posted
2. vendor and tax are booked
3. asset draft / capital WIP is created
4. user reviews asset details
5. asset is capitalized

## Recommended Accounting Model

## Expense Purchase

At posting:

- DR Expense
- DR Input GST
- CR Vendor

## Inventory Purchase

At posting:

- inventory move created
- inventory / purchase accounting posted
- vendor liability created

## Asset Purchase

Recommended future model:

### At purchase posting

- DR Capital WIP / Asset Clearing
- DR Input GST
- CR Vendor

### At capitalization

- DR Fixed Asset
- CR Capital WIP / Asset Clearing

This is preferable to direct capitalization because it supports:

- pending installation
- approval delays
- multi-invoice capitalization
- better control over put-to-use timing

## Product-Level vs Line-Level Control

### Recommended Approach

Use:

- product-level classification as default
- line-level override only where needed

### Why

Product-level:

- keeps behavior consistent
- reduces user error

Line-level override:

- handles exceptions
- gives flexibility in special cases

## Suggested Implementation Order

1. Phase 1: Classification foundation
2. Phase 2: Expense purchase flow
3. Phase 3: Asset intake flow
4. Phase 4: Asset review/capitalization
5. Phase 5: Controls, alerts, and reports

## Why This Order

This order solves the biggest pain first:

- not every purchase should become inventory

It also handles both of your real-world examples:

- computer for office use -> asset flow
- food expense for office use -> expense flow

## Interim Operating Guidance

Until full automation is built:

- resale items -> continue through inventory flow
- office food / pantry / repairs -> use expense-oriented purchase handling
- office-use capital goods -> create purchase invoice, then create asset manually in Asset module

## Success Criteria

The phased design should be considered successful when:

1. Non-trading expenses no longer land in inventory.
2. Asset purchases no longer depend on manual re-entry without reference linkage.
3. Inventory contains only real stock items.
4. Fixed assets contain only true capital purchases.
5. Purchase classification is visible, understandable, and enforceable.

## Summary

The complete design direction is:

- classify purchases first
- route by business intent
- inventory for stock
- expense for immediate consumption
- asset for long-term internal use

This is the cleanest path for Finacc to support both:

- operational stock control
- capital asset accounting

without mixing the two.
