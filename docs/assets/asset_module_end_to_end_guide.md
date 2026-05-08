# Asset Module End-to-End Guide

## Purpose

This document explains the Asset module in simple business language.

It is written for:

- business owners
- finance users
- admin users
- implementation teams
- support teams
- UAT users

This guide explains:

- what the Asset module is for
- what each screen does
- the correct business flow
- when to use each screen
- common mistakes to avoid

This guide does not explain code.

---

## What The Asset Module Means

In simple terms, the Asset module is used to manage long-term business items such as:

- computers
- machinery
- furniture
- vehicles
- office equipment
- leased assets
- capital work in progress

These are not normal day-to-day expense items.

They are items whose value usually stays in the business for a longer period and may need:

- capitalization
- depreciation
- impairment
- transfer
- disposal
- reporting

Simple explanation:

- purchase expense is for regular spending
- asset management is for important items that stay on the books over time

---

## Quick Flow

In most businesses, the Asset module should be used in this order:

1. Decide asset policy in `Asset Settings`
2. Create ledger structure needed for asset accounting
3. Create asset groups in `Asset Category Master`
4. Create individual records in `Asset Master`
5. Capitalize approved assets
6. Run and post depreciation in `Depreciation Run`
7. Review reports in:
   - `Fixed Asset Register`
   - `Depreciation Schedule`
   - `Asset Events`
   - `Asset History`
8. Use impairment, transfer, or disposal actions whenever the asset lifecycle changes

---

## Main Screens

The Asset module has these main screens:

- `Asset Settings`
- `Asset Category Master`
- `Asset Master`
- `Depreciation Run`
- `Fixed Asset Register`
- `Depreciation Schedule`
- `Asset Events`
- `Asset History`

---

## 1. Asset Settings

Screen:

- `Asset Settings`

Route:

- `assetsettings`
- `asset-settings`

What this screen is for:

- This is the control room for the whole Asset module.
- It defines default behavior, governance rules, and posting behavior.

What users do here:

- set default document code for asset creation
- set default document code for disposal
- choose save behavior such as draft, confirm, or post
- set default depreciation method
- define default useful life
- define default residual value percentage
- define depreciation posting day
- set capitalization threshold
- choose whether assets are auto-numbered
- choose whether asset tag is mandatory
- choose whether multiple asset books are allowed
- choose whether depreciation can auto-post
- choose whether impairment tracking is enabled
- define capitalization and depreciation policy rules

Important policy examples:

- whether capitalization is allowed manually, by posting, or both
- whether backdated capitalization is blocked, warned, or allowed
- whether depreciation lock is strict
- whether negative net book value should be blocked
- whether users can manually override depreciation

Who should use it:

- finance controller
- implementation consultant
- admin user

When to use it:

- during initial setup
- before go-live
- whenever policy changes

Simple explanation:

- This screen decides the rules.
- The operational screens follow those rules.

It is not for:

- creating asset groups
- creating asset records
- posting monthly depreciation directly

---

## 2. Asset Category Master

Screen:

- `Asset Category Master`

Route:

- `assetcategorymaster`
- `asset-category-master`

What this screen is for:

- This screen is used to create asset groups.
- A category acts like a template for similar assets.

Examples:

- Computers
- Furniture
- Plant and Machinery
- Vehicles
- Right-of-Use Assets
- Capital WIP

What users do here:

- create category code and name
- choose asset nature
- choose depreciation method
- define useful life
- define residual value rules
- set capitalization threshold if needed
- attach the proper ledgers for that category

Why this screen matters:

- categories keep asset setup clean and consistent
- they reduce data-entry mistakes in the asset master
- they control which ledgers and depreciation rules should be used

Who should use it:

- finance setup team
- implementation team
- admin user

When to use it:

- before creating asset masters
- when a new asset class is introduced
- when accounting classification changes

Simple explanation:

- If Asset Master is the record of one item, Asset Category Master is the rulebook for that item type.

It is not for:

- entering individual laptops or machines one by one
- monthly depreciation posting

---

## 3. Asset Master

Screen:

- `Asset Master`

Route:

- `assetmaster`
- `asset-master`

What this screen is for:

- This is the working screen for individual asset records.
- One asset record usually means one actual business item or one capitalized unit.

What users do here:

- create a new asset
- edit draft or active asset details
- assign category and ledger
- fill acquisition date and business details
- capture location, department, and custodian
- record gross block and useful life details
- capitalize the asset
- record impairment
- transfer ownership or operational location
- dispose the asset
- open asset history
- archive old records

Typical fields users maintain:

- asset code
- asset name
- asset tag
- serial number
- model or manufacturer
- acquisition date
- capitalization date
- put-to-use date
- gross block
- useful life
- depreciation method
- residual value
- location
- department
- custodian

Bulk import:

- This screen also supports bulk import for asset masters.
- Use bulk import only when the master data is already cleaned and approved.

Who should use it:

- finance operations team
- fixed asset team
- admin user
- implementation team during data migration

When to use it:

- whenever a new asset is introduced
- when an existing asset changes lifecycle
- during opening data migration

Simple explanation:

- This is the central working register for each asset item.

It is not for:

- deciding company-wide policy
- monthly depreciation scheduling for all assets together

---

## 4. Depreciation Run

Screen:

- `Depreciation Run`

Route:

- `depreciationrun`
- `depreciation-run`

What this screen is for:

- This screen is used to calculate and post depreciation for a period.

What users do here:

- create a depreciation run
- choose period from and period to
- set posting date
- choose depreciation method if required
- calculate depreciation lines
- review calculated values
- post the run
- cancel a run if needed

What happens during a depreciation run:

1. the system finds eligible assets
2. it calculates depreciation for the selected period
3. it prepares line-wise values
4. it posts accounting impact if the run is posted

Why this screen matters:

- depreciation is not just a report
- it is an accounting event
- posted depreciation changes accumulated depreciation and net book value

Who should use it:

- finance users
- fixed asset accountants
- month-end closing team

When to use it:

- monthly close
- quarter close
- year-end close
- whenever approved depreciation needs to be posted

Simple explanation:

- This is the processing screen for depreciation.

It is not for:

- creating asset masters
- designing categories
- viewing long-term history only

---

## 5. Fixed Asset Register

Screen:

- `Fixed Asset Register`

Route:

- `fixedassetregister`
- `fixed-asset-register`

What this screen is for:

- This is the main summary report for active assets.

What users can review here:

- asset code
- asset name
- category
- status
- acquisition date
- capitalization date
- put-to-use date
- gross block
- accumulated depreciation
- impairment
- net book value
- ledger
- location
- department
- custodian

Who should use it:

- management
- auditors
- finance users
- support teams

When to use it:

- monthly review
- audit preparation
- reconciliation
- asset verification exercises

Simple explanation:

- This is the main business view of the asset book.

It is not for:

- running depreciation
- changing asset policy

---

## 6. Depreciation Schedule

Screen:

- `Depreciation Schedule`

Route:

- `depreciationschedule`
- `depreciation-schedule`

What this screen is for:

- This report shows depreciation movement line by line across run periods.

What users review here:

- run code
- asset code
- asset name
- period from
- period to
- depreciation amount
- closing net book value
- run status

Who should use it:

- finance users
- auditors
- closing team

When to use it:

- after depreciation runs
- during reconciliations
- when checking how a specific asset was depreciated

Simple explanation:

- If the Fixed Asset Register shows the current position, Depreciation Schedule shows the periodic depreciation movement.

---

## 7. Asset Events

Screen:

- `Asset Events`

Route:

- `assetevents`
- `asset-events`

What this screen is for:

- This report shows major lifecycle events of assets.

Typical event types:

- capitalization
- depreciation
- impairment
- disposal

What users review here:

- which event happened
- when it happened
- how much value was affected
- which asset was impacted

Who should use it:

- finance users
- audit teams
- controllers

When to use it:

- event tracking
- audit support
- exception review

Simple explanation:

- This is the activity timeline report for assets.

---

## 8. Asset History

Screen:

- `Asset History`

Route:

- `assethistory`
- `asset-history`

What this screen is for:

- This is the detailed story of one asset.

What users review here:

- creation
- capitalization
- depreciation history
- impairment history
- disposal details
- journal impact

Why this screen matters:

- when someone asks, "What happened to this asset?"
- this is the best place to answer that question

Who should use it:

- finance users
- auditors
- support users
- implementation teams during issue analysis

When to use it:

- whenever one asset needs detailed investigation
- while checking journal impact
- during audit queries

Simple explanation:

- This is the biography of one asset.

---

## Recommended Business Flow

For a normal business, the practical flow should be:

1. Configure `Asset Settings`
2. Create or review asset ledgers
3. Create `Asset Category Master`
4. Create records in `Asset Master`
5. Capitalize only approved assets
6. Run `Depreciation Run` at period close
7. Review reports
8. Record impairment, transfer, or disposal whenever needed

---

## Simple Example

Suppose the company buys a laptop for office use.

The business flow would usually be:

1. `Asset Settings` already defines policy
2. `Asset Category Master` already has a category called `Computers`
3. User creates one record in `Asset Master`
4. User enters acquisition date, gross value, and tag
5. User capitalizes the asset after approval
6. Finance posts monthly depreciation through `Depreciation Run`
7. User can later see:
   - current value in `Fixed Asset Register`
   - monthly movement in `Depreciation Schedule`
   - event trail in `Asset Events`
   - full story in `Asset History`

---

## What Should Be Ready Before Go-Live

Before live usage, make sure these are ready:

- Asset feature is enabled for the tenant
- user roles have the correct asset permissions
- asset settings are reviewed and approved
- required ledgers exist in the chart of accounts
- asset categories are created
- numbering policy is decided
- asset tag policy is decided
- opening asset data is cleaned
- depreciation method policy is finalized
- month-end ownership is assigned

---

## Suggested Ownership

Suggested business ownership:

- `Asset Settings` -> finance controller or admin
- `Asset Category Master` -> implementation team or finance master-data owner
- `Asset Master` -> fixed asset operations team
- `Depreciation Run` -> finance closing team
- reports -> finance, management, audit, and support

---

## Common Mistakes To Avoid

- creating assets before categories are finalized
- capitalizing items that should be normal expenses
- posting depreciation without checking run period
- leaving ledger mapping inconsistent across categories
- changing policy after go-live without impact review
- skipping asset tags when the business requires physical verification
- using bulk import without validating the source file first
- disposing an asset without confirming proceeds and gain/loss impact

---

## Frequently Asked Questions

### 1. What is the difference between acquisition and capitalization?

Simple answer:

- acquisition means the item was obtained
- capitalization means the item is officially moved into the asset book

### 2. What is the difference between asset category and asset master?

Simple answer:

- category is the rule/template
- asset master is one actual item

### 3. Why is depreciation run separate from asset master?

Simple answer:

- asset master stores the asset
- depreciation run processes periodic accounting

### 4. When should impairment be used?

Simple answer:

- when asset value needs to be reduced because recoverable value has fallen

### 5. What is disposal?

Simple answer:

- disposal means the asset has left the business through sale, scrap, write-off, or retirement

---

## Layman Summary

If someone wants the Asset module explained in one minute:

- `Asset Settings` decides the rules
- `Asset Category Master` creates asset groups
- `Asset Master` creates and manages individual asset records
- `Depreciation Run` calculates and posts depreciation
- `Fixed Asset Register` shows current asset position
- `Depreciation Schedule` shows depreciation movement
- `Asset Events` shows important lifecycle events
- `Asset History` shows the full story of one asset

In short:

- this module helps the business control asset value from start to finish

