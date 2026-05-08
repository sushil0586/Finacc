# Asset Ledger Mapping Guide

## Purpose

This document explains, in simple business language, what the asset posting ledgers are used for in Finacc.

It is meant for:

- finance users
- implementation teams
- support teams
- business owners reviewing setup

This guide explains:

- what each asset ledger means
- where the ledger is used
- why the ledger is important
- what happens during asset posting
- what should be configured before go-live

This guide does not explain code.

---

## What This Setup Does

When the Asset module is used properly, Finacc does not only store master data.

It also creates accounting impact during important lifecycle actions such as:

- capitalization
- depreciation
- impairment
- disposal

That means the Asset module is not only a register.

It is also an accounting module.

For that reason, correct ledger mapping is required.

If the ledger setup is wrong:

- asset value may go to the wrong balance sheet ledger
- depreciation may hit the wrong expense account
- impairment may be posted incorrectly
- disposal gain or loss may be incorrect
- reports may not match accounting books

---

## Where To Configure It

The asset ledger mapping is mainly controlled in:

- `Asset Category Master`

Supporting policy is controlled in:

- `Asset Settings`

Important note:

- categories hold the most important posting ledgers
- settings control the rules

Simple explanation:

- `Asset Settings` decides how the system should behave
- `Asset Category Master` decides which ledgers each type of asset should use

---

## Core Asset Accounting Events

There are four main accounting events in the Asset module:

1. Capitalization
2. Depreciation
3. Impairment
4. Disposal

Each event needs the correct ledgers.

---

## 1. Capitalization Posting

What capitalization means:

- the item is officially moved into the asset book
- it starts being treated as a capital asset instead of a draft or WIP item

What the system does:

- debits the asset ledger
- credits a counter ledger selected during capitalization

Simple example:

- Asset cost = `100,000`
- debit `Asset Ledger`
- credit `Counter Ledger`

Common business counter ledgers:

- CWIP clearing
- vendor clearing
- purchase adjustment ledger
- temporary capitalization clearing ledger

Important point:

- the asset category should already point to the correct asset ledger
- the user must choose the correct counter ledger during capitalization

---

## 2. Depreciation Posting

What depreciation means:

- asset value is charged to expense gradually over useful life

What the system does during depreciation posting:

- debits `Depreciation Expense Ledger`
- credits `Accumulated Depreciation Ledger`

Simple example:

- Monthly depreciation = `2,500`
- debit `Depreciation Expense`
- credit `Accumulated Depreciation`

Why this matters:

- expense goes to profit and loss
- accumulated depreciation reduces effective carrying value on the balance sheet

Important point:

- these ledgers are not selected manually every month
- they are taken from the asset category

---

## 3. Impairment Posting

What impairment means:

- the asset has lost value beyond normal depreciation

What the system does:

- debits `Impairment Expense Ledger`
- credits `Impairment Reserve Ledger`

Simple example:

- impairment = `15,000`
- debit `Impairment Expense`
- credit `Impairment Reserve`

Why this matters:

- impairment is separate from normal depreciation
- businesses use it when an asset becomes damaged, obsolete, or less recoverable

Important point:

- impairment tracking should be enabled in `Asset Settings`
- the asset category must define both impairment ledgers

---

## 4. Disposal Posting

What disposal means:

- the asset leaves the books because it was sold, scrapped, retired, or written off

What the system does:

- clears the original asset cost
- clears accumulated depreciation
- clears impairment reserve if present
- records sale proceeds if any
- posts gain or loss on disposal

Possible postings involved:

- `Asset Ledger`
- `Accumulated Depreciation Ledger`
- `Impairment Reserve Ledger`
- `Proceeds Ledger` chosen at disposal time
- `Gain on Sale Ledger`
- `Loss on Sale Ledger`

Simple example:

- gross asset cost = `100,000`
- accumulated depreciation = `70,000`
- net book value = `30,000`
- sale proceeds = `35,000`
- gain = `5,000`

Result:

- asset is removed from books
- gain is posted to gain ledger

If sale proceeds were `25,000`:

- loss = `5,000`
- loss is posted to loss ledger

---

## Asset Category Ledger Fields

Each asset category can hold these important ledgers:

- `Asset Ledger`
- `Accumulated Depreciation Ledger`
- `Depreciation Expense Ledger`
- `Impairment Expense Ledger`
- `Impairment Reserve Ledger`
- `CWIP Ledger`
- `Gain on Sale Ledger`
- `Loss on Sale Ledger`

Below is the business meaning of each one.

---

## 1. Asset Ledger

What it means:

- the main balance sheet ledger where asset cost is held

Used in:

- capitalization
- disposal

Simple explanation:

- this is the main ledger of the asset itself

Examples:

- Computer Equipment
- Furniture and Fixtures
- Plant and Machinery
- Vehicles

If this is wrong:

- the asset may appear in the wrong asset class on the balance sheet

---

## 2. Accumulated Depreciation Ledger

What it means:

- the contra ledger that stores total depreciation posted so far

Used in:

- depreciation
- disposal

Simple explanation:

- this ledger reduces the carrying value of the asset over time

If this is wrong:

- depreciation may not appear correctly against the asset block

---

## 3. Depreciation Expense Ledger

What it means:

- the profit and loss ledger where periodic depreciation expense is booked

Used in:

- depreciation run posting

Simple explanation:

- this is where monthly or periodic depreciation hits the expense side

If this is wrong:

- P&L may show expense in the wrong head

---

## 4. Impairment Expense Ledger

What it means:

- the P&L ledger used when asset value is reduced through impairment

Used in:

- impairment posting

Simple explanation:

- this is the expense side of impairment

If this is wrong:

- impairment impact may be mixed with normal depreciation or another expense bucket

---

## 5. Impairment Reserve Ledger

What it means:

- the balance sheet or contra-style ledger used to hold impairment reserve

Used in:

- impairment posting
- disposal of an impaired asset

Simple explanation:

- this is the reserve side of impairment

If this is wrong:

- impaired assets may not clear properly during disposal

---

## 6. CWIP Ledger

What it means:

- capital work in progress ledger

When it is useful:

- when the asset is under construction or not yet ready for full capitalization

Examples:

- building under construction
- major machinery installation in progress
- large projects not yet ready for productive use

Simple explanation:

- this is the temporary holding ledger before final capitalization

---

## 7. Gain on Sale Ledger

What it means:

- the income ledger used when disposal proceeds are more than net book value

Used in:

- disposal with gain

Simple explanation:

- this ledger records profit on asset sale or retirement outcome

---

## 8. Loss on Sale Ledger

What it means:

- the expense ledger used when disposal proceeds are less than net book value

Used in:

- disposal with loss

Simple explanation:

- this ledger records the shortfall on disposal

---

## Suggested Ledger Mapping By Business Meaning

Below is a practical mapping idea.

You should adjust names based on your chart of accounts.

### For normal tangible assets

- `Asset Ledger` -> Fixed Asset ledger for that class
- `Accumulated Depreciation Ledger` -> Accumulated Depreciation ledger
- `Depreciation Expense Ledger` -> Depreciation Expense ledger
- `Impairment Expense Ledger` -> Impairment Loss ledger
- `Impairment Reserve Ledger` -> Impairment Reserve ledger
- `Gain on Sale Ledger` -> Profit on Sale of Asset
- `Loss on Sale Ledger` -> Loss on Sale of Asset

### For CWIP assets

- `CWIP Ledger` -> Capital Work in Progress
- `Asset Ledger` -> final fixed asset ledger after capitalization

### For leased or right-of-use assets

- use separate asset and depreciation ledgers if reporting must remain separate from owned assets

---

## Example End-to-End Accounting Flow

Suppose a business buys a machine for `500,000`.

### Step 1. Asset is created

- no final accounting impact yet if still in draft

### Step 2. Asset is capitalized

- debit `Machine Asset Ledger`
- credit `Capitalization Counter Ledger`

### Step 3. Monthly depreciation is posted

- debit `Depreciation Expense`
- credit `Accumulated Depreciation`

### Step 4. Asset is impaired by `25,000`

- debit `Impairment Expense`
- credit `Impairment Reserve`

### Step 5. Asset is sold

The system:

- removes original gross block
- clears accumulated depreciation
- clears impairment reserve if applicable
- records sale proceeds
- records gain or loss

---

## Seeded Example Ledgers In Standard Setup

In a typical seeded setup, Finacc may create example ledgers such as:

- `Computer Equipment`
- `Peripheral Equipment`
- `Accumulated Depreciation - Assets`
- `Impairment Reserve`
- `Depreciation Expense`
- `Gain on Sale of Asset`
- `Loss on Sale of Asset`
- `Impairment Expense`

Important note:

- these are example starting points
- every business should still review and approve the final mapping

---

## Go-Live Checklist For Ledger Mapping

Before going live, confirm:

- every active asset category has an asset ledger
- every depreciable category has depreciation expense ledger
- every depreciable category has accumulated depreciation ledger
- every impairment-enabled category has impairment expense ledger
- every impairment-enabled category has impairment reserve ledger
- every disposable category has gain and loss on sale ledgers
- CWIP categories have CWIP treatment clearly defined
- finance approves the chart-of-account placement of all these ledgers

---

## Common Mistakes To Avoid

- using one generic ledger for all asset classes without finance approval
- forgetting accumulated depreciation ledger
- forgetting impairment reserve ledger
- posting depreciation to a direct expense ledger that should be grouped elsewhere
- leaving disposal gain/loss ledgers blank
- capitalizing to the wrong asset class ledger
- not separating CWIP from final asset class when business needs that separation

---

## FAQ

### 1. Why is accumulated depreciation separate from asset ledger?

Simple answer:

- because the original asset cost should stay visible
- depreciation is tracked separately as reduction over time

### 2. Why do we need separate gain and loss ledgers?

Simple answer:

- because disposal outcome may be profit or loss
- finance usually wants both tracked separately

### 3. Is impairment the same as depreciation?

Simple answer:

- no
- depreciation is planned reduction over useful life
- impairment is additional reduction because value has fallen

### 4. Can one category use the same ledgers as another category?

Simple answer:

- yes, if finance policy allows it
- but many businesses prefer separate ledgers for better reporting

---

## Layman Summary

If someone wants the ledger mapping explained in one minute:

- `Asset Ledger` holds the asset cost
- `Accumulated Depreciation Ledger` holds total depreciation to date
- `Depreciation Expense Ledger` books periodic expense
- `Impairment Expense Ledger` and `Impairment Reserve Ledger` handle value loss
- `Gain on Sale Ledger` and `Loss on Sale Ledger` handle disposal result
- `CWIP Ledger` is used when the asset is not fully ready yet

In short:

- the category decides where each asset lifecycle event will hit the books

