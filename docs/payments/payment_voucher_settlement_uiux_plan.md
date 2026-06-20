# Payment Voucher Settlement UI/UX Plan

Date: 2026-06-19

## Purpose

This document defines how the Payment Voucher UI should behave for:

- `AGAINST_BILL`
- `ADVANCE`
- `ON_ACCOUNT`

The backend settlement model is already acceptable. The goal here is to align the frontend workflow and terminology with that backend truth so users can understand funding, allocation, and advance adjustment without confusion.

---

## 1. Product Position

Payment Voucher is not just a cash-entry form.

It is a settlement workspace where the user answers three different questions depending on payment type:

1. Which liability is being settled now?
2. How much of that settlement comes from cash?
3. How much comes from existing vendor credit or advance?

The UI should make those questions explicit and should not force the user to reverse-engineer accounting logic from warning banners.

---

## 2. Backend Truth We Must Preserve

For `AGAINST_BILL`, the backend effectively works with:

- `Settlement Support = Cash Paid + Settlement Adjustments + Advance Consumed`
- `Allocated Bill Amount must match Settlement Support`

For advance adjustment rows:

- each consumed advance must point to a target bill
- total consumed for a bill cannot exceed that bill's allocated amount
- total consumed from an advance cannot exceed that advance's open balance

For `ADVANCE` and `ON_ACCOUNT`:

- cash paid must be positive
- posting can create or maintain vendor advance balance
- allocation may be optional or policy-driven

The frontend must never present a workflow that contradicts these rules.

---

## 3. Core UX Principles

### 3.1 Bill settlement comes before funding breakdown

For `AGAINST_BILL`, users think first in terms of bills to settle, not first in terms of cash entered.

The UI should therefore drive the user through:

1. choose bills
2. choose settlement amount against those bills
3. decide how much old advance to consume
4. let system derive required cash

### 3.2 Old advances are a funding source, not a separate settlement universe

Users should never feel they are doing one allocation for bills and another unrelated balancing exercise for advances.

The UI should present old advances as:

- vendor credit available for selected bill settlement
- usable against selected bill rows
- part of the funding mix

### 3.3 The page should always answer one question clearly

At any moment the page should tell the user:

- what total is being settled
- how much is funded by old advances
- how much is funded by cash
- whether anything is still unfunded or overfunded

### 3.4 Labels must be accounting-true and operator-friendly

Avoid ambiguous labels like:

- `Unallocated` when the real issue is missing funding
- `Settlement Target` when the user is looking at cash and bills together without context

Prefer:

- `Bill Settlement Target`
- `Advance Applied`
- `Cash Required`
- `Funding Gap`
- `Overfunded`

---

## 4. Recommended Page Model

The page should be divided into four layers.

### 4.1 Voucher Header

This section captures:

- voucher no
- voucher date
- branch
- paid from
- paid to vendor
- payment mode
- reference no / txn id
- narration
- payment type
- supply type when relevant

This section should not attempt to explain settlement math.

### 4.2 Settlement Intent

This section defines what the user is trying to settle.

Depending on payment type:

- `AGAINST_BILL`: open bills are the primary focus
- `ADVANCE`: no prior bill selection required by default
- `ON_ACCOUNT`: no bill required at entry time unless policy demands future linking

### 4.3 Funding Breakdown

This section explains how settlement is funded.

It should show:

- bill settlement target
- advance applied
- adjustment effect
- runtime TDS effect
- cash required or cash entered
- funding gap or surplus

### 4.4 Posting Readiness

This section explains:

- what is valid
- what is missing
- what is only a warning
- what will happen on post

---

## 5. Behavior By Payment Type

## 5.1 `AGAINST_BILL`

### User intent

The user wants to settle specific vendor bills now.

### Primary workflow

1. Select vendor
2. Load open bill rows
3. User enters settlement amounts on one or more bills
4. System calculates `Bill Settlement Target`
5. User optionally applies old advances against those selected bills
6. System computes `Cash Required`
7. User confirms payment mode and cash amount
8. User posts

### Page behavior

The page should center around the bill grid, not the cash field.

The main summary should read like this:

- `Bill Settlement Target`
- `Advance Applied`
- `Adjustment Effect`
- `Runtime TDS`
- `Cash Required`
- `Funding Status`

### Recommended formulas

For `AGAINST_BILL`:

- `Bill Settlement Target = Sum of bill row settled amounts`
- `Advance Applied = Sum of selected advance adjustment amounts`
- `Adjustment Effect = Net plus/minus settlement adjustments`
- `Cash Required = Bill Settlement Target - Advance Applied - Adjustment Effect`
- `Funding Gap = Bill Settlement Target - (Advance Applied + Adjustment Effect + Cash Paid)`

If runtime TDS adds support, it should be visible as part of `Adjustment Effect` or as a separate support line, but never hidden.

### What should drive the page

The page should be driven by bill allocation totals first.

Cash should be residual by default.

This is the opposite of the current confusing behavior where the user enters cash first and then the system increases the target after advance selection.

### Advance application behavior

Old advances should only be usable against bills that already have a positive settlement amount.

Recommended actions:

- `Auto Apply Oldest Advances`
- `Apply Full Advance`
- `Split Across Selected Bills`
- `Clear Applied Advances`

Recommended rules:

- do not default a new advance row to the first bill unless exactly one bill is selected
- if multiple bills are selected, ask the system to split by remaining unfunded bill amount
- visually show each bill's funding mix:
  - bill settlement amount
  - funded by old advance
  - funded by cash

### Recommended warnings

Use these messages instead of vague mismatch warnings:

- `Selected bills total 63,000.00 but only 15,000.00 is funded. Apply old advances or increase cash.`
- `Advance usage for bill PI/PINV/2026/1001 exceeds the bill settlement amount by 33,000.00.`
- `Advance ADV-003 has 12,000.00 available but only 5,000.00 is needed for selected bills.`

### Recommended UI actions

- `Auto Allocate Bills`
- `Auto Apply Advances`
- `Use Suggested Cash`
- `Balance Now`

`Balance Now` should be a guided helper that:

1. allocates bills
2. applies usable old advances FIFO
3. derives cash residual

---

## 5.2 `ADVANCE`

### User intent

The user is paying money to the vendor before a bill is being settled now.

### Primary workflow

1. Select vendor
2. Enter advance cash amount
3. Select supply type
4. If service or mixed and GST logic applies, show advance tax block
5. Save or post

### Page behavior

The bill allocation grid should not be the primary workspace here.

Instead, the page should show:

- `Advance Amount`
- `GST on Advance` where relevant
- `Expected Vendor Credit To Be Created`

### Summary language

Use:

- `Cash Paid`
- `Advance Credit To Create`
- `Advance Taxable Value`
- `Advance GST`
- `Posting Outcome`

Do not show bill settlement language unless policy explicitly requires allocation even for advances.

### Optional allocation behavior

If policy requires advance allocation:

- show an optional secondary section named `Pre-link to Future Bills`
- make it clearly advisory or policy-driven
- never make it look like normal against-bill settlement

### Posting readiness

The page should explain:

- this payment will create vendor advance balance
- this amount will remain open for future bill adjustment

---

## 5.3 `ON_ACCOUNT`

### User intent

The user is paying the vendor without linking it to a bill at the time of entry, but this is not the explicit tax-aware `ADVANCE` flow.

### Primary workflow

1. Select vendor
2. Enter cash amount
3. Save or post
4. System creates vendor credit / on-account balance according to backend policy

### Page behavior

This page should be much lighter than `AGAINST_BILL`.

It should show:

- `Cash Paid`
- `On-account Credit To Remain Open`
- `Future Settlement Use`

### Optional linking

If policy allows later settlement only:

- do not force allocations now

If policy requires allocation:

- show a policy note:
  `This entity requires on-account payments to be linked before posting.`

### Summary language

Use:

- `On-account Amount`
- `Credit Created`
- `Linked Now`
- `Credit Remaining Open`

---

## 6. Shared Allocation Rules Across All Modes

### 6.1 Allocation should mean one thing

The word `allocation` should always mean linking value to bill rows.

It should not be reused to mean:

- cash entry
- old advance pick
- adjustment creation

### 6.2 Funding and allocation are different concepts

Use this distinction consistently:

- `Allocation`: which bill is being settled
- `Funding`: how that settlement is being financed

### 6.3 Visual model per bill row

For `AGAINST_BILL`, each selected bill row should eventually show:

- bill open amount
- current settle amount
- from old advance
- from cash
- from adjustment if relevant
- remaining unfunded

This is much easier to understand than a separate advance table that users mentally have to reconcile.

---

## 7. Recommended Screen Architecture

## 7.1 Header summary strip

For `AGAINST_BILL`, top summary should be:

- `Bills Selected`
- `Bill Settlement Target`
- `Advance Applied`
- `Cash Required`
- `Cash Entered`
- `Funding Gap`

For `ADVANCE`, top summary should be:

- `Advance Amount`
- `GST Impact`
- `Credit To Create`

For `ON_ACCOUNT`, top summary should be:

- `On-account Amount`
- `Credit Remaining Open`

## 7.2 Section order

Recommended section order:

1. core details
2. payment-type-aware settlement intent
3. funding breakdown
4. adjustments and runtime TDS
5. posting readiness
6. vendor AP context and history

The current page mixes these ideas too early and makes the user calculate mentally.

---

## 8. Recommended Action Design

### `AGAINST_BILL`

Primary actions:

- `Auto Allocate Bills`
- `Auto Apply Advances`
- `Use Suggested Cash`
- `Save Draft`
- `Post`

Secondary actions:

- `Clear Bills`
- `Clear Advances`
- `Clear Funding`

### `ADVANCE`

Primary actions:

- `Save Draft`
- `Post Advance`

Secondary actions:

- `Preview GST Impact`
- `Review Advance Credit`

### `ON_ACCOUNT`

Primary actions:

- `Save Draft`
- `Post On-account Payment`

Secondary actions:

- `Review Future Credit Effect`

---

## 9. Error and Warning Language

The page should move from technical mismatch messages to operator messages.

### Good examples

- `You selected 3 bills totaling 63,000.00. Current funding covers only 15,000.00.`
- `Old advances can only be applied to bills that already have a settlement amount.`
- `Cash is 12,000.00 higher than needed for the selected bills. This excess will remain as vendor credit if posting is allowed.`
- `This voucher will create a new vendor advance balance of 15,000.00.`

### Avoid

- `Allocation is not balanced`
- `Advance usage exceeds visible settle amount`

Those may still appear in logs or debug detail, but not as the primary operator narrative.

---

## 10. Vendor-A Scenario Walkthrough

Example:

- Vendor has 3 old advances totaling `48,000.00`
- User wants to pay `15,000.00` cash now
- User wants to settle bills totaling `63,000.00`

Correct UI flow:

1. user selects bills totaling `63,000.00`
2. system shows `Bill Settlement Target = 63,000.00`
3. user clicks `Auto Apply Advances`
4. system applies `48,000.00` old advances to selected bills
5. system computes `Cash Required = 15,000.00`
6. user confirms `Cash Entered = 15,000.00`
7. status becomes `Balanced`

Wrong UI flow to avoid:

1. user enters `15,000.00` cash first
2. system shows settlement around that amount
3. user picks old advances
4. system suddenly shows `Unallocated 48,000.00`

The second experience is technically explainable but operationally poor.

---

## 11. Implementation Plan

## Phase 1: Terminology and summary cleanup

- rename summary labels
- distinguish `bill target` from `cash paid`
- introduce `funding gap` language
- remove misleading `unallocated` wording in `AGAINST_BILL`

## Phase 2: Workflow reordering

- make bill grid primary for `AGAINST_BILL`
- derive cash from bill target and applied advances
- keep advance panel disabled until bill settlement exists

## Phase 3: Advance automation

- add `Auto Apply Advances`
- split advances across selected bills by remaining unfunded amount
- show per-bill funding mix

## Phase 4: Mode-specific layouts

- simplify `ADVANCE` page
- simplify `ON_ACCOUNT` page
- only show relevant sections per payment type

## Phase 5: Readiness and operator messaging

- improve validation copy
- add `posting outcome` preview
- make policy-driven requirements clearer

---

## 12. Acceptance Criteria

The redesign is successful when:

- a user can explain the page without reading backend logic
- `AGAINST_BILL` users start from bills, not from cash
- advance consumption feels like funding, not like a second balancing problem
- `ADVANCE` and `ON_ACCOUNT` flows are visibly lighter than bill-settlement flow
- warning copy uses business language
- frontend totals always reconcile to backend posting rules

---

## 13. Recommended Next Build Order

Build in this order:

1. `AGAINST_BILL` summary and terminology cleanup
2. `AGAINST_BILL` bill-first funding flow
3. auto-apply advance behavior
4. `ADVANCE` screen simplification
5. `ON_ACCOUNT` screen simplification
6. shared validation and readiness copy polish

This gives the biggest operator benefit first while keeping the backend unchanged.
