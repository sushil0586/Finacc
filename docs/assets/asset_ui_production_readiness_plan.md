# Asset UI Production Readiness Plan

Date: 2026-06-02

## Purpose

This document defines the frontend production-readiness plan for the Asset module.

The goal is not only to make the screens look better, but to make them easier to operate in a live finance environment.

The main UI intent is:

- one clear responsibility per screen
- less horizontal crowding
- fewer competing grids in the same visual band
- more disciplined use of headers, forms, and actions
- consistent, production-ready layout behavior across desktop and laptop screens

This plan should be used alongside the hardening blueprint, not instead of it.

---

## 1. Design Rules

These rules apply across the full Asset module.

### 1.1 One major job per screen

Each screen should have one primary purpose:

- maintain setup
- review transactions
- perform lifecycle action
- review history
- consume reports

If a screen is trying to do all of those at once, we should split responsibilities into sections, dialogs, tabs, or follow-on views.

### 1.2 One primary grid per page

As a default rule:

- use one major grid per page
- avoid two heavy grids in the same horizontal layout
- move secondary data into cards, drawers, dialogs, or row detail

### 1.3 Prefer vertical flow over wide composition

We should avoid long side-by-side regions that force the user to scan left and right repeatedly.

Preferred flow:

1. header
2. scope / filter bar
3. summary / guidance
4. main grid or main form
5. selected-item detail or action workspace below

### 1.4 Consistent header structure

Every asset screen should aim for:

- short eyebrow
- page title
- one-line purpose statement
- scope chips where relevant
- primary page actions grouped to the right or below

### 1.5 Form discipline

Forms should:

- use 1 column on small screens
- use 2 columns max for standard desktop forms
- use section cards for long forms
- keep helper text close to the field
- keep validation immediately below the field

### 1.6 Action clarity

Governed actions like:

- capitalize
- impair
- dispose
- reverse

should not compete visually with routine actions like:

- edit
- duplicate
- archive
- view history

Primary lifecycle actions should sit in their own workspace.

### 1.7 Table discipline

Main grids should show only the fields needed for:

- identification
- quick status review
- first-level decision making

Secondary fields should move out of the main grid.

---

## 2. Screen Responsibility Map

### 2.1 Asset Master

Primary responsibility:

- maintain asset records
- select an asset
- run governed lifecycle actions against that asset

Should not try to do:

- full reporting
- too many row-level actions in the grid
- deep form editing and precheck review in the same cramped area

### 2.2 Asset Category Master

Primary responsibility:

- maintain reusable category definitions
- manage ledger defaults and policy overrides

### 2.3 Asset Settings

Primary responsibility:

- manage scope-level policy and default values

### 2.4 Depreciation Run

Primary responsibility:

- prepare, review, and post depreciation runs

### 2.5 Fixed Asset Register

Primary responsibility:

- browse and export asset register reporting

### 2.6 Asset History

Primary responsibility:

- explain the lifecycle and journal story of a selected asset

### 2.7 Asset Events

Primary responsibility:

- show lifecycle activity across multiple assets

### 2.8 Asset Location / Custodian

Primary responsibility:

- operational reassignment and tracking

---

## 3. Execution Order

Recommended order:

1. Asset Master
2. Asset Category Master
3. Asset Settings
4. Depreciation Run
5. Fixed Asset Register
6. Asset History
7. Asset Events
8. Asset Location / Custodian

Why this order:

- it starts with the highest operational impact
- it starts with the most overloaded screen
- it lets us establish a reusable layout language early

---

## 4. First Screen To Finalize: Asset Master

`Asset Master` should be the first screen we finalize fully.

Why:

- it is the operational center of the module
- it currently has the heaviest mix of list, form, policy, action, and reversal responsibilities
- it is the most likely place where horizontal density hurts usability
- solving it well gives us a design pattern for the other screens

---

## 5. Asset Master Current Pain Points

Based on the current screen structure:

- the main grid is too wide for comfortable laptop use
- the row action area is overloaded
- the screen mixes selection, editing, lifecycle action, reversal, guidance, and policy display at once
- there is still too much decision density in one continuous experience
- several important secondary fields are visible in the main grid even though they are not first-decision fields

The screen is strong functionally, but it still needs a cleaner operational shape.

---

## 6. Asset Master Target Structure

The final structure should be:

### 6.1 Header

Contains:

- title
- scope chips
- one-line purpose text

### 6.2 Scope and filter card

Contains:

- financial year
- subentity
- search
- category
- status
- review queue
- apply / reset
- new asset
- bulk import

This area stays compact and does not compete with the detail workspace.

### 6.3 Guidance and policy strip

Keep only the most useful high-level context here:

- active runtime policy summary
- short usage guidance

This should remain lightweight and not become a second dashboard.

### 6.4 Primary asset grid

This remains the only major grid on the page.

Recommended visible columns:

- asset code
- asset name
- category
- status
- acquisition date
- capitalization date
- gross block
- net book value
- quick open / select action

Move out of the primary grid:

- location
- department
- custodian
- ledger
- accumulated depreciation
- impairment
- most row-level lifecycle actions

Those belong in the selected asset workspace.

### 6.5 Selected asset workspace

This should open below the grid or in a consistent full-width dialog, but with clearer internal structure.

Recommended sections:

1. Asset Summary
2. Edit Asset
3. Traceability and Operational Completeness
4. Lifecycle Action Center
5. Reversal and Correction

This workspace should feel like a guided review area, not a long generic form.

---

## 7. Asset Master Detailed Layout Plan

### 7.1 Asset Summary card

Purpose:

- identify the selected asset quickly
- reduce the need to scan back to the grid

Fields to show:

- asset code
- asset name
- category
- current status
- gross block
- accumulated depreciation
- impairment amount
- net book value
- purchase intake reference when applicable

### 7.2 Edit Asset card

Purpose:

- maintain the master record

Break the form into sections:

1. Identity and Classification
2. Dates and Valuation
3. Operational Details
4. References and Notes

Fields should not be presented as one uninterrupted block.

### 7.3 Traceability and completeness card

Purpose:

- show advisory policy nudges
- show missing operational completeness fields

Should contain:

- traceability advisories
- policy provenance cards
- purchase review readiness where relevant

This keeps advisory content separate from core form inputs.

### 7.4 Lifecycle Action Center

Purpose:

- keep capitalization, impairment, transfer, and disposal together
- show action precheck and impact clearly

This should include:

- action selection
- action-specific form
- precheck output
- impact summary
- final action button

This is the right place for governance-heavy actions.

### 7.5 Reversal and correction card

Purpose:

- isolate correction activity from normal posting activity

Should include:

- reverse capitalization
- reverse impairment
- reverse disposal
- latest posting snapshot
- blocker / warning display

Reversal should feel serious and deliberate, not like a small utility button cluster.

---

## 8. Asset Master Interaction Rules

### 8.1 Grid rules

- clicking code or name selects the asset
- row actions should be reduced to a very small set
- heavy lifecycle actions should open in the selected workspace, not all stay inline

### 8.2 Form rules

- save action belongs to the edit form area only
- section titles should tell the user why the fields matter
- inline validation stays directly below the field

### 8.3 Action rules

- action precheck should appear before final post
- warnings should not be hidden inside dialogs without context
- action impact should remain visible while the user decides

### 8.4 Reversal rules

- reversal must remain a separate, explicit correction flow
- reversal buttons should not visually overpower normal edit actions

---

## 9. Asset Master Visual Standards

### 9.1 Density

Use a calmer spacing model:

- more breathing room between cards
- fewer compact chips competing at once
- clearer section separation

### 9.2 Forms

All textboxes, dropdowns, date inputs, and numeric fields should share:

- consistent height
- consistent label spacing
- consistent error placement
- consistent helper-text styling

### 9.3 Tables

Tables should:

- keep key columns visible
- avoid forcing horizontal scroll for normal use
- move low-priority details out of the base row

### 9.4 Headers

Use short, purposeful headings.

Avoid:

- repeated long guidance blocks
- too many pill labels competing for attention

### 9.5 Dialogs

Dialogs should have:

- one clear purpose
- one dominant action
- visible context
- no overloaded header action bars

---

## 10. Screen-by-Screen Standards After Asset Master

Once `Asset Master` is finalized, apply the same discipline to the remaining screens.

### 10.1 Asset Category Master

Target changes:

- keep one simple category grid
- use a cleaner grouped edit dialog
- separate:
  - basic definition
  - depreciation defaults
  - ledger mapping
  - traceability overrides
  - accounting overrides

### 10.2 Asset Settings

Target changes:

- turn the long settings flow into grouped policy sections
- add stronger hierarchy between defaults and governance controls
- reduce the feeling of a flat policy spreadsheet

### 10.3 Depreciation Run

Target changes:

- keep parameter entry compact
- show precheck and run outcome clearly
- keep one result grid

### 10.4 Fixed Asset Register

Target changes:

- make it report-first
- reduce editing affordances
- strengthen filter and export usability

### 10.5 Asset History

Target changes:

- make the timeline more readable
- keep journal effect below the main lifecycle story

### 10.6 Asset Events

Target changes:

- emphasize event readability and filters
- reduce noise around secondary metadata

### 10.7 Asset Location / Custodian

Target changes:

- make reassignment the central task
- reduce any unrelated setup or reporting burden

---

## 11. Delivery Method

For each screen, we should follow the same sequence:

1. define the primary responsibility
2. remove or relocate competing responsibilities
3. reduce horizontal density
4. simplify the main grid
5. group forms into clear sections
6. improve visual hierarchy
7. verify desktop and laptop usability
8. run typecheck and screen-specific testing

---

## 12. Immediate Next Step

The next execution step should be:

1. finalize the `Asset Master` target layout blocks
2. decide exactly which columns stay in the primary grid
3. decide which actions stay inline versus move into the selected asset workspace
4. implement the screen in one focused pass
5. validate before moving to the next asset screen

This screen should become the reference implementation for the rest of the Asset module.
