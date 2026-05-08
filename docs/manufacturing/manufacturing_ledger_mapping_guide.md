# Manufacturing Ledger Mapping Guide

## Purpose

This document explains, in simple business language, what the manufacturing posting ledgers are used for in Finacc.

It is meant for:

- finance users
- implementation teams
- support teams
- business owners reviewing setup

It does not explain code. It explains:

- what each manufacturing ledger means
- why the system needs it
- what happens during work order posting
- what users should configure in the Static Account Settings screen

---

## What This Setup Does

When a manufacturing work order is posted, Finacc does two things:

1. It updates stock.
2. It creates accounting entries.

Stock movement alone is not enough for ERP accounting. Finance also needs to know:

- raw material value has been consumed
- production cost has moved into WIP
- finished goods value has been created
- extra production cost like labour or power has been absorbed

That is why these ledger mappings are required.

---

## Where To Configure It

Go to:

- `Admin`
- `Static Account Settings`
- `Manufacturing` section

You will see these base codes:

- `MANUFACTURING_WIP`
- `MANUFACTURING_CONSUMPTION`
- `MANUFACTURING_OVERHEAD_ABSORPTION`
- `MANUFACTURING_FINISHED_GOODS`

If Manufacturing Settings uses `Standard cost with variances`, you will also need:

- `MANUFACTURING_MATERIAL_VARIANCE`
- `MANUFACTURING_YIELD_VARIANCE`

If Manufacturing Settings leaves any additional cost type as non-capitalized, you will also need:

- `MANUFACTURING_ADDITIONAL_COST_EXPENSE`

Each required code must be mapped to a ledger.

---

## Manufacturing Accounting Modes

Manufacturing Settings controls how output valuation works.

### 1. `Actual cost to output`

Meaning:

- finished goods receive actual consumed material cost plus additional cost
- no separate variance journal is posted

Required ledgers:

- `MANUFACTURING_WIP`
- `MANUFACTURING_CONSUMPTION`
- `MANUFACTURING_OVERHEAD_ABSORPTION`
- `MANUFACTURING_FINISHED_GOODS`

### 2. `Standard cost with variances`

Meaning:

- finished goods receive standard material cost plus entered additional cost
- material difference goes to a material variance ledger
- output / yield difference goes to a yield variance ledger

Required ledgers:

- the same four base ledgers above
- `MANUFACTURING_MATERIAL_VARIANCE`
- `MANUFACTURING_YIELD_VARIANCE`

Additional note:

- if any additional cost type is not capitalized, map `MANUFACTURING_ADDITIONAL_COST_EXPENSE` too

---

## Simple Business Flow

Suppose you consume:

- Raw material value: `470`
- Additional production cost: `50`

Total production cost becomes:

- `520`

When you post the work order, Finacc will:

1. move material cost into production
2. absorb additional production cost
3. capitalize finished goods value
4. clear WIP at the end of the posting

This creates proper accounting trace for production.

---

## Ledger Meaning In Simple Language

## 1. `MANUFACTURING_WIP`

Suggested meaning:

- Work in Progress
- Production in Process
- WIP Control

What it is for:

- This is the temporary holding ledger for production cost.
- Raw material value and additional production cost first come here.
- Once finished goods are created, WIP is cleared out.

Simple way to think about it:

- This ledger is the "cost bucket while goods are under production."

Typical use:

- Debit when material or cost enters production
- Credit when production is completed and value moves to finished goods

Business example:

- Sugar bulk goes into packing
- Labour is added
- All of that sits in WIP until the final packed stock is created

If this ledger is wrong:

- your production cost flow will not be visible correctly
- finance may not be able to track production value in process

---

## 2. `MANUFACTURING_CONSUMPTION`

Suggested meaning:

- Raw Material Consumption
- Production Consumption
- Material Issue to Production

What it is for:

- This ledger represents the value of materials consumed by manufacturing.
- When raw material is issued into production, this ledger gets credited in the current posting design.

Simple way to think about it:

- This is the accounting side of "we used stock for production."

Typical use:

- It shows that raw material value has left the consumption side and moved into WIP.

Business example:

- 10 kg sugar and 10 pouches are consumed for one work order
- their total value is reflected through this ledger

If this ledger is wrong:

- material usage accounting may land in the wrong place
- production cost reporting becomes confusing

---

## 3. `MANUFACTURING_OVERHEAD_ABSORPTION`

Suggested meaning:

- Production Overhead Absorption
- Manufacturing Overhead Applied
- Production Cost Allocation

What it is for:

- This ledger handles additional production cost entered on the work order.
- Examples:
  - labour
  - electricity
  - fuel
  - packing support cost
  - other shop-floor expenses

Simple way to think about it:

- This is the accounting side of "extra production cost added to the job."

Typical use:

- Additional cost is debited into WIP
- This ledger is credited as the offset in the current posting design

Business example:

- Material consumed: `470`
- Labour and electricity: `50`
- Total finished goods cost: `520`

If this ledger is wrong:

- additional cost may not be captured properly
- finished goods may look under-costed or accounting may become unclear

---

## 4. `MANUFACTURING_FINISHED_GOODS`

Suggested meaning:

- Finished Goods Inventory
- Manufactured Stock
- Production Output Inventory

What it is for:

- This ledger receives the value of completed production.
- Main output and byproduct capitalization are posted here in the current design.

Simple way to think about it:

- This is the accounting side of "production is complete and stock is now ready."

Typical use:

- Debit when finished goods are created
- Value comes from the total production cost after applying output costing rules

Business example:

- Packed sugar stock is created and becomes available for sale
- the value of that stock is reflected here

If this ledger is wrong:

- finished stock value may appear under the wrong ledger
- production completion accounting will be misleading

---

## 5. `MANUFACTURING_MATERIAL_VARIANCE`

Suggested meaning:

- Material Variance
- Production Consumption Variance
- Standard vs Actual Material Difference

What it is for:

- This ledger is used only when output valuation is set to `Standard cost with variances`.
- It captures the difference between standard material cost and actual material consumed.

Simple way to think about it:

- This shows whether the job used more or less material value than expected.

Business example:

- standard material cost expected: `470`
- actual material consumed: `479`
- material variance posted: `9`

If this ledger is wrong:

- finance cannot isolate over-consumption or favorable material savings correctly

---

## 6. `MANUFACTURING_YIELD_VARIANCE`

Suggested meaning:

- Yield Variance
- Production Output Variance
- Standard Output Recovery Difference

What it is for:

- This ledger is also used only in `Standard cost with variances` mode.
- It captures the cost impact of producing more or less output than standard expectation.

Simple way to think about it:

- This shows whether output yield matched what the BOM and standard cost expected.

Business example:

- standard output expectation: `10`
- actual output received: `9.8`
- yield variance is posted separately instead of hiding inside finished goods value

If this ledger is wrong:

- yield loss or favorable output variance cannot be reviewed clearly by finance or management

---

## 7. `MANUFACTURING_ADDITIONAL_COST_EXPENSE`

Suggested meaning:

- Manufacturing Additional Cost Expense
- Factory Expense Not Capitalized
- Production Period Expense

What it is for:

- This ledger is used when a manufacturing additional cost type should not increase finished goods value.
- Examples may include electricity, temporary shop-floor support cost, or other costs the business wants to expense immediately.

Simple way to think about it:

- Some production-related costs belong in inventory value.
- Some belong in the current period expense.
- This ledger handles the second case.

Business example:

- Labour is capitalized into FG cost
- Electricity is not capitalized
- electricity amount posts to this expense ledger while labour still goes into WIP / FG cost

If this ledger is wrong:

- non-capitalized manufacturing costs may either disappear from reporting or get mixed into inventory value incorrectly

---

## What Happens During Posting

In simple words, posting does this:

1. Material cost moves into `MANUFACTURING_WIP`
2. Material issue side is reflected through `MANUFACTURING_CONSUMPTION`
3. Additional production cost moves into `MANUFACTURING_WIP`
4. Offset for that extra cost goes through `MANUFACTURING_OVERHEAD_ABSORPTION`
5. Finished goods value is debited to `MANUFACTURING_FINISHED_GOODS`
6. `MANUFACTURING_WIP` is cleared at the end

If output valuation is `Standard cost with variances`, then:

7. material variance is posted to `MANUFACTURING_MATERIAL_VARIANCE`
8. yield variance is posted to `MANUFACTURING_YIELD_VARIANCE`

If some additional cost types are marked as non-capitalized, then:

9. those cost lines are debited to `MANUFACTURING_ADDITIONAL_COST_EXPENSE`

This means:

- stock is updated
- accounting is updated
- work order gets a posting entry id

---

## What Users Will See In The Screen

Inside `Static Account Settings`:

- each manufacturing row shows a code
- user selects the ledger to map
- user saves the row

Once saved, manufacturing posting can use those ledgers automatically.

If permission is available, users can:

- view the manufacturing mapping rows
- change ledger mapping
- bulk save mappings

---

## Setup Advice

- Start with `Actual cost to output` if the customer is new to manufacturing accounting.
- Move to `Standard cost with variances` only after BOM quantities and expected material standards are stable.
- Always map the two variance ledgers before enabling standard-cost valuation.
- validate missing setup

---

## What Happens If Mapping Is Missing

If one of these mappings is not set:

- manufacturing posting may fail
- the work order can remain saved but not post successfully

So the recommended onboarding rule is:

- complete manufacturing ledger mapping before go-live

---

## Recommended Setup Approach

Use a finance-led naming pattern like:

- `Manufacturing WIP`
- `Raw Material Consumption`
- `Manufacturing Overhead Absorption`
- `Finished Goods Inventory`

Recommended checklist:

1. Create or confirm the required ledgers in financial masters.
2. Open `Static Account Settings`.
3. Go to the `Manufacturing` group.
4. Map all four rows.
5. Save.
6. Test with one sample work order.
7. Verify stock and ledger effect before live usage.

---

## Example Setup

Example only. Final names depend on your chart of accounts.

- `MANUFACTURING_WIP` -> `Production WIP`
- `MANUFACTURING_CONSUMPTION` -> `Raw Material Consumption`
- `MANUFACTURING_OVERHEAD_ABSORPTION` -> `Production Overhead Absorption`
- `MANUFACTURING_FINISHED_GOODS` -> `Finished Goods Inventory`

---

## Common Mistakes To Avoid

1. Do not map all four codes to the same ledger unless finance has approved that design.
2. Do not map manufacturing finished goods to a sales ledger.
3. Do not leave overhead absorption unmapped if additional production costs will be used.
4. Do not assume stock movement alone is enough; accounting mapping is also required.
5. Do not test only draft save. Always test actual posting.

---

## Current Scope Note

This is the current manufacturing accounting foundation.

It already supports:

- stock consumption
- finished goods receipt
- WIP-based posting flow
- additional cost absorption
- journal reversal on unpost

It does not yet mean the system has full advanced manufacturing accounting such as:

- stage-wise WIP accounting
- detailed variance ledger strategy
- work-center costing
- subcontracting accounting

Those can be added in later phases.

---

## Summary

These four mappings make manufacturing posting financially meaningful.

In plain language:

- `MANUFACTURING_WIP` = cost while production is in process
- `MANUFACTURING_CONSUMPTION` = value of material used
- `MANUFACTURING_OVERHEAD_ABSORPTION` = extra production cost applied
- `MANUFACTURING_FINISHED_GOODS` = value of completed manufactured stock

If these are mapped properly, the manufacturing module can post both stock impact and accounting impact in a controlled way.
