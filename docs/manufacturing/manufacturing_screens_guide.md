# Manufacturing Screens Guide

## Purpose

This document explains each manufacturing-related screen in simple business language.

It answers:

- what each screen is for
- who should use it
- when to use it
- what should be configured there

This guide is written for:

- business users
- finance users
- inventory users
- implementation teams
- UAT teams

---

## Quick Flow

In simple terms, manufacturing setup and usage usually follows this order:

1. Configure manufacturing behavior in `Manufacturing Settings`
2. Configure posting ledgers in `Static Account Settings`
3. Define process steps in `Route Workspace`
4. Define product recipe in `BOM Workspace`
5. Create and run production in `Work Order Entry`
6. Review saved or posted work orders in `Work Order Browser`

---

## 1. Manufacturing Settings

Screen:

- `Manufacturing Settings`

Route:

- `manufacturingsettings`
- `manufacturing-settings`

What this screen is for:

- This is the control room for manufacturing behavior.
- It decides how the work order screen should behave by default.

What users do here:

- set default work order document code
- choose whether work orders save as draft or auto-post
- decide whether BOM materials should auto-fill into work orders
- decide whether users can manually change exploded materials
- decide whether negative stock should be blocked
- decide batch and expiry validation rules
- choose whether finished goods are valued at actual cost or standard cost with variances
- choose which additional cost types should be capitalized and which should post to expense

Who should use it:

- implementation team
- inventory head
- finance/admin user

When to use it:

- during first-time setup
- before go-live
- when policy changes

Simple explanation:

- This screen defines the rules of the manufacturing process.

It is not for:

- creating BOMs
- creating work orders
- daily production entry

---

## 2. Static Account Settings

Screen:

- `Static Account Settings`

Manufacturing section inside that screen:

- `Manufacturing`

Route:

- `staticaccountsettings`

What this screen is for:

- This screen is used to connect manufacturing posting to finance ledgers.
- Without this setup, manufacturing stock may work but accounting posting will not be complete.

What users do here:

- map `MANUFACTURING_WIP`
- map `MANUFACTURING_CONSUMPTION`
- map `MANUFACTURING_OVERHEAD_ABSORPTION`
- map `MANUFACTURING_FINISHED_GOODS`

If Manufacturing Settings uses `Standard cost with variances`, also map:

- `MANUFACTURING_MATERIAL_VARIANCE`
- `MANUFACTURING_YIELD_VARIANCE`

If any additional cost type is kept non-capitalized, also map:

- `MANUFACTURING_ADDITIONAL_COST_EXPENSE`

Who should use it:

- finance team
- implementation consultant
- admin user

When to use it:

- during finance setup
- before posting work orders in live usage
- when ledger structure changes

Simple explanation:

- This screen tells the system which ledger should be used for each manufacturing accounting role.

It is not for:

- daily production entry
- product recipe setup
- operation tracking

---

## 3. Route Workspace

Screen:

- `Route Workspace`

Route:

- `manufacturing-routes`

What this screen is for:

- This screen defines the step-by-step production process.
- A route answers the question:
  - what stages does production go through?

What users do here:

- create route code and name
- define steps like mixing, packing, drying, inspection
- decide step order
- mark whether QC is required
- mark whether a step is mandatory
- optionally capture standard duration

Who should use it:

- production supervisor
- implementation team
- process owner

When to use it:

- when a product needs a defined sequence of operations
- before creating routed BOMs
- when production process changes

Simple explanation:

- If BOM is the recipe, route is the process path.

Example:

- Step 1: Mixing
- Step 2: Packing
- Step 3: QC

It is not for:

- material consumption entry
- accounting setup
- final posting

---

## 4. BOM Workspace

Screen:

- `BOM Workspace`

Route:

- `manufacturing-boms`

What this screen is for:

- This screen defines the recipe of a finished product.
- BOM means Bill of Material.

What users do here:

- choose the finished product
- define output quantity
- attach a route if needed
- add material lines
- define quantity for each material
- define waste percent
- keep BOM active or inactive

Who should use it:

- production planner
- inventory controller
- implementation team

When to use it:

- before creating work orders from standard recipe
- when material recipe changes
- when new finished products are introduced

Simple explanation:

- This screen answers:
  - what materials are needed to make one unit or one batch of output?

Example:

- Finished product: Sugar 1kg pack
- Materials:
  - sugar bulk
  - pouch
  - label

It is not for:

- daily posting
- operator execution
- ledger mapping

---

## 5. Work Order Entry

Screen:

- `Work Order Entry`

Routes:

- `productionorder`
- `manufacturing-work-order-entry`

What this screen is for:

- This is the main production transaction screen.
- It is where actual manufacturing work is entered, saved, executed, posted, unposted, or cancelled.

What users do here:

- create a new work order
- choose BOM or create manual work order
- select source and destination location
- enter production date and reference number
- review or change material lines
- enter output lines
- run route operations
- approve or reject QC steps
- add additional production cost
- save draft
- post final work order
- unpost or cancel when allowed

Who should use it:

- production user
- inventory operator
- supervisor
- QA approver
- finance reviewer for posting outcome

When to use it:

- during actual production entry
- for repacking
- for assembly
- for batch creation
- for correcting or reposting production transactions

Simple explanation:

- This is the operational heart of manufacturing.

Main sections inside this screen:

### Header

Used for:

- production date
- work order number
- BOM selection
- planned output quantity
- reference number
- source and destination location
- narration

### Status panel

Used for:

- current work order status
- posting entry id
- posted by / unposted by / cancelled by details
- quick audit visibility

### Totals panel

Used for:

- input quantity
- output quantity
- waste
- material cost
- additional cost
- recovery value
- variance view
- derived finished goods cost

### Operations section

Used for:

- step-by-step route execution
- start / complete / skip step
- QC approve / reject
- operator-level progress

### Materials section

Used for:

- actual material consumption
- batch and expiry capture where required
- viewing BOM exploded lines

### Outputs section

Used for:

- finished goods quantity
- byproduct quantity
- output batch details

### Additional costs section

Used for:

- labour
- electricity
- packing support cost
- other production cost

This screen is not only for data entry. It is also the screen that finalizes production posting.

---

## 6. Work Order Browser

Screen:

- `Work Order Browser`

Route:

- `manufacturing-work-order-list`

What this screen is for:

- This screen is used to review already saved work orders.
- It is a list-and-preview screen for manufacturing transactions.

What users do here:

- search work orders
- filter by code, reference, BOM, or status
- open an existing work order
- review materials and key numbers
- identify draft, posted, or cancelled documents

Who should use it:

- production supervisor
- inventory reviewer
- support team
- finance reviewer

When to use it:

- to review older production documents
- to reopen a draft
- to inspect posted work orders
- to check posting entry id and basic production summary

Simple explanation:

- This is the lookup and review screen for manufacturing documents.

It is not for:

- defining BOMs
- defining routes
- accounting configuration

---

## Which Screen To Use For What

If the user wants to do this:

- set manufacturing rules -> `Manufacturing Settings`
- set manufacturing ledgers -> `Static Account Settings`
- define process steps -> `Route Workspace`
- define material recipe -> `BOM Workspace`
- enter actual production -> `Work Order Entry`
- review saved production -> `Work Order Browser`

---

## Recommended Role-wise Usage

### Finance / Accounts

Best screens:

- `Static Account Settings`
- `Manufacturing Settings`
- `Work Order Browser`

Typical purpose:

- ledger mapping
- posting review
- audit review

### Production Planner

Best screens:

- `Route Workspace`
- `BOM Workspace`
- `Work Order Browser`

Typical purpose:

- process definition
- recipe setup
- planning review

### Production Operator

Best screen:

- `Work Order Entry`

Typical purpose:

- create or complete production work
- capture actual quantities
- update step progress

### Supervisor / QA

Best screens:

- `Work Order Entry`
- `Work Order Browser`

Typical purpose:

- route progress control
- QC approval/rejection
- exception review

---

## Suggested Training Order

For new users, train in this order:

1. `Manufacturing Settings`
2. `Static Account Settings`
3. `Route Workspace`
4. `BOM Workspace`
5. `Work Order Entry`
6. `Work Order Browser`

This order works because:

- first define rules
- then define finance setup
- then define process
- then define recipe
- then enter production
- then review results

---

## Summary

Each manufacturing screen has a different purpose:

- `Manufacturing Settings` = rules
- `Static Account Settings` = ledger mapping
- `Route Workspace` = process steps
- `BOM Workspace` = recipe
- `Work Order Entry` = actual production transaction
- `Work Order Browser` = saved document review

If teams use the right screen for the right purpose, setup becomes cleaner and daily manufacturing flow becomes easier to control.
## Manufacturing Hub

This is the new landing screen for manufacturing users.

Use this screen when you want one place to start instead of opening manufacturing pages from the inventory hub.

What it is for:
- opening manufacturing settings
- opening static account settings for manufacturing ledger mapping
- opening route workspace
- opening BOM workspace
- opening work order entry
- opening work order browser

Who should use it:
- manufacturing admin
- production planner
- operator supervisor
- implementation and support team during setup

When to use it:
- at the start of manufacturing setup
- when training users
- when moving between BOM, routing, work orders, and posting setup

## Manufacturing Summary

This is the first reporting screen for manufacturing.

Use this screen when you want a quick health check of manufacturing operations without opening each work order one by one.

What it is for:
- checking whether manufacturing ledger mapping is complete
- seeing draft, posted, cancelled, and QC-pending counts
- reviewing recent work orders
- seeing top material consumption rows
- seeing top output rows
- seeing which output valuation mode is active
- seeing variance totals when standard-cost valuation is enabled

Who should use it:
- production manager
- implementation team
- finance reviewer
- support team during go-live

When to use it:
- before starting live posting
- during daily production review
- during UAT to confirm setup and activity are aligned

## Material Consumption Report

This report shows what material was consumed in manufacturing work orders.

What it is for:
- checking actual material issue line by line
- reviewing waste quantity
- reviewing material consumption value
- tracking batch usage for consumed items

Who should use it:
- production manager
- stores team
- costing reviewer

## Output And Yield Report

This report shows how much output was planned and how much was actually produced.

What it is for:
- comparing standard output vs actual output
- reviewing yield variance
- reviewing actual unit cost
- reviewing output line details including byproduct or scrap output
- understanding whether output is being reviewed under actual-cost or standard-cost variance mode

Who should use it:
- production manager
- costing reviewer
- implementation team during UAT

## Posting Audit Report

This report shows the posting lifecycle of manufacturing work orders.

What it is for:
- checking which work orders are posted
- checking posting entry references
- checking who unposted or cancelled a work order
- reviewing manufacturing audit trail in one place

Who should use it:
- finance reviewer
- support team
- implementation team

## WIP And Cost Summary

This report gives a cost-focused view of manufacturing work orders.

What it is for:
- checking draft work orders that still sit in WIP
- reviewing posted manufacturing cost snapshots
- reviewing additional cost loading
- reviewing material and yield variance at work-order level
- reviewing yield variance value when variance-ledger mode is enabled

Who should use it:
- finance reviewer
- costing reviewer
- production manager
