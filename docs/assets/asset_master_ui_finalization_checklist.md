# Asset Master UI Finalization Checklist

Date: 2026-06-02

## Purpose

This checklist translates the Asset UI production-readiness plan into an implementation-ready guide for the `Asset Master` screen.

It is intended to help us finalize one screen fully before moving to the next screen in the Asset module.

This checklist focuses on:

- screen responsibility
- layout hierarchy
- grid simplification
- workspace structure
- action placement
- production-readiness quality gates

---

## 1. Final Target For This Screen

The `Asset Master` screen should become:

- the operational home for asset records
- the primary place to select and maintain an asset
- the guided workspace for governed lifecycle actions

It should not behave like:

- a report grid overloaded with operational actions
- a long horizontally dense form
- a mixed-action surface where edit, posting, and reversal compete equally

---

## 2. Primary Responsibility

The final responsibility of `Asset Master` is:

1. filter and find the correct asset
2. select the asset
3. review the asset summary
4. edit the asset master data
5. perform lifecycle actions through guided prechecks
6. perform correction through deliberate reversal flows

Anything outside that should be reduced, relocated, or deprioritized visually.

---

## 3. Page Structure To Implement

The final page should follow this order:

1. Page header
2. Scope and filter card
3. Lightweight policy and usage guidance
4. Primary asset grid
5. Selected asset workspace

The page should avoid:

- multiple heavy regions fighting for attention at once
- dense side-by-side action surfaces
- too many inline action buttons inside the grid

---

## 4. Header Checklist

Keep:

- eyebrow
- page title
- scope chips

Improve:

- add one short purpose line under the title
- keep scope chips compact and meaningful

Avoid:

- a header that behaves like a dashboard
- too many action buttons in the top header itself

Acceptance check:

- a user should understand the purpose of the screen in less than 5 seconds

---

## 5. Scope And Filter Card Checklist

Keep these controls:

- financial year
- subentity
- search
- category
- status
- review queue

Keep these actions:

- apply
- reset
- new asset
- bulk import

Implementation rules:

- all filters should live in one card
- controls should wrap cleanly on smaller widths
- primary actions should be visually separated from filter fields

Avoid:

- a second filter row that feels disconnected
- too many small buttons scattered between fields

Acceptance check:

- the filter card should work comfortably on a laptop without sideways scanning

---

## 6. Policy And Guidance Strip Checklist

Keep:

- active runtime policy summary
- short operational guidance

Reduce:

- too many simultaneous pills
- repeated explanatory text

Implementation rules:

- show only the most decision-relevant policy items
- keep copy short
- preserve vertical rhythm between guidance and the grid

Acceptance check:

- this section should support the screen, not dominate it

---

## 7. Primary Grid Checklist

This is the most important simplification step.

### 7.1 Columns to keep in the main grid

Keep:

- asset code
- asset name
- category
- status
- acquisition date
- capitalization date
- gross block
- net book value
- open / select

Optional if space remains:

- put to use date

### 7.2 Columns to remove from the main grid

Move out of the grid:

- location
- department
- custodian
- ledger
- accumulated depreciation
- impairment amount
- long purchase reference detail

These belong in the selected asset workspace.

### 7.3 Row action cleanup

Current row actions are too dense.

Final inline row actions should be minimal:

- open / select
- maybe one contextual quick action if genuinely valuable

Move out of row actions:

- capitalize
- impair
- transfer
- dispose
- reverse capitalization
- reverse impairment
- reverse disposal
- archive
- history

These should live in the selected asset workspace.

### 7.4 Grid behavior rules

- clicking code or name opens the selected asset workspace
- selected row state should remain visible
- grid must remain readable without horizontal stress on a normal laptop

Acceptance checks:

- no “action wall” at the far-right edge
- scanning the main grid should feel calm and fast

---

## 8. Selected Asset Workspace Checklist

The selected asset workspace should become the controlled action area for the screen.

It may remain a full-width dialog if that is the best current fit, but the internal structure must be cleaner.

Final section order:

1. Asset Summary
2. Edit Asset
3. Traceability and Completeness
4. Lifecycle Action Center
5. Reversal and Correction

---

## 9. Asset Summary Card Checklist

Purpose:

- give instant context after selection
- reduce the need to look back at the grid

Show:

- asset code
- asset name
- category
- current status
- purchase intake flag when relevant
- gross block
- accumulated depreciation
- impairment amount
- net book value
- posting batch references if useful and not noisy

Move here from the grid:

- accumulated depreciation
- impairment amount

Acceptance check:

- a user should know “what asset am I editing and what state is it in?” immediately

---

## 10. Edit Asset Card Checklist

This remains the main maintenance area.

### 10.1 Section structure

Implement these sections:

1. Identity and Classification
2. Dates and Valuation
3. Operational Details
4. References and Notes

### 10.2 Field placement

Identity and Classification:

- subentity
- category
- ledger
- status
- asset code
- asset name
- asset tag

Dates and Valuation:

- acquisition date
- capitalization date
- put to use date
- depreciation start date
- quantity
- gross block
- residual value
- useful life months
- depreciation method
- depreciation rate

Operational Details:

- location
- department
- custodian

References and Notes:

- serial number
- manufacturer
- model number
- vendor account
- purchase document number
- external reference
- notes

### 10.3 Layout rules

- use two columns max
- let notes span full width
- keep labels above inputs
- show helper text only where it adds real value

Acceptance checks:

- no section should feel like a random mixed field dump
- the form should remain readable without zooming out

---

## 11. Traceability And Completeness Card Checklist

This card should separate “recommended completeness” from core data entry.

Keep here:

- traceability advisories
- traceability policy provenance
- purchase review readiness

Do not mix these items directly into the edit form unless they are true field errors.

Visual rule:

- advisories should be noticeable but lighter than blocking action warnings

Acceptance check:

- users should understand what is recommended versus what is mandatory

---

## 12. Lifecycle Action Center Checklist

This should become the home for all governed lifecycle actions.

Keep here:

- capitalize
- impair
- transfer
- dispose

### 12.1 Internal layout

Recommended order:

1. action picker
2. action context card
3. action-specific form
4. precheck result
5. impact summary
6. final action button

### 12.2 Action behavior rules

- action precheck must be visible before submit
- blocked actions must explain why
- warnings must remain visible through decision time
- the final post button should appear only in this workspace, not scattered elsewhere

### 12.3 Transfer handling

Transfer is operational, but it should still stay here for consistency instead of becoming a competing standalone row action.

Acceptance check:

- a user should feel guided through the action, not dropped into a small form fragment

---

## 13. Reversal And Correction Checklist

This should be a separate card or clearly separate subsection.

Keep here:

- reverse capitalization
- reverse impairment
- reverse disposal
- latest posting snapshot
- precheck blockers
- warnings
- impact preview

Visual rules:

- correction actions should look deliberate
- they should not sit in the same visual cluster as routine edit actions

Acceptance check:

- reversal should feel controlled and auditable, not casual

---

## 14. Action Placement Rules

### 14.1 Keep in the grid

- select / open

### 14.2 Keep in workspace header

- close
- maybe duplicate
- maybe history

### 14.3 Keep inside the edit area

- save asset

### 14.4 Keep inside lifecycle action center

- capitalize
- impair
- transfer
- dispose

### 14.5 Keep inside correction area

- reverse capitalization
- reverse impairment
- reverse disposal

### 14.6 Move out of overloaded button clusters

- archive should not compete with reversal actions in a crowded header row
- history should not appear both everywhere and nowhere; pick one clear home

---

## 15. Visual Cleanup Checklist

### 15.1 Spacing

- increase space between major cards
- reduce cramped clusters of pills and buttons
- keep section rhythm consistent

### 15.2 Input consistency

All textboxes, selects, dates, and numeric fields should share:

- same height
- same radius
- same label spacing
- same error spacing

### 15.3 Button hierarchy

Use clearer levels:

- primary
- secondary
- danger
- link

Do not let every action look equally important.

### 15.4 Typography

- stronger section headings
- lighter helper copy
- readable table and form text sizing

### 15.5 Responsiveness

- no major layout should require side scrolling on common laptop widths
- workspace sections should stack cleanly on narrower screens

---

## 16. Implementation Phases

### Phase 1: Grid simplification

- reduce columns
- remove most row-level actions
- keep selection strong

### Phase 2: Workspace restructuring

- introduce or reorganize summary, edit, advisory, action, and correction sections

### Phase 3: Action placement cleanup

- move lifecycle and reversal actions into the right workspace areas

### Phase 4: Visual polish

- spacing
- card hierarchy
- forms
- responsive cleanup

### Phase 5: Verification

- test normal asset create/edit flow
- test purchase intake review flow
- test capitalization precheck flow
- test reversal flow
- test laptop-width usability

---

## 17. Definition Of Done

`Asset Master` is considered finalized for this tranche when:

1. the grid is readable without horizontal overload
2. row-level actions are minimal and purposeful
3. the selected asset workspace has clear section responsibilities
4. lifecycle actions feel guided and governed
5. reversal actions feel deliberate and separate
6. headers, dropdowns, textboxes, and spacing feel production-ready
7. the screen works cleanly on standard laptop and desktop widths
8. frontend behavior still matches backend governance and precheck contracts

---

## 18. After This Screen

Once this checklist is completed, use the same pattern for:

- Asset Category Master
- Asset Settings
- Depreciation Run
- Fixed Asset Register
- Asset History
- Asset Events
- Asset Location / Custodian

This screen should become the reference implementation for the rest of the Asset module.
