# Asset UI Design Rollout Plan

Date: 2026-06-02

## Purpose

This document defines the complete UI rollout plan for the Asset module after the `Asset Master` and `Asset Category Master` screens were modernized.

The goal is to make every remaining asset screen follow the same design language, information hierarchy, spacing discipline, and operational structure as the finalized master screens.

This is not a backend plan.

This is not a business-logic change plan.

This is a frontend productization plan.

The intent is:

- one recognizable design system across the whole Asset module
- one clear responsibility per screen
- high-signal information visible early
- less wasted vertical space
- fewer overloaded pages
- consistent use of cards, filters, KPI bands, tables, dialogs, and action areas

This document should be used together with:

- `asset_module_hardening_blueprint.md`
- `asset_ui_production_readiness_plan.md`
- `asset_master_ui_finalization_checklist.md`

---

## 1. Baseline We Will Reuse

The `Asset Master` work is now the reference implementation.

The following patterns should be treated as the Asset UI baseline:

- premium page shell with softened gradients and deeper card hierarchy
- strong popup focus with proper modal mask and background falloff
- wizard-style structured editing where long forms exist
- KPI summary band near the top of the page
- scope card before the main working area
- one major grid per page
- decision-first information ordering
- secondary help and policy content moved lower or into dedicated dialogs
- clean separation between routine maintenance and governed actions
- separate focused dialogs for secondary responsibilities

If a later screen deviates from this, it should do so intentionally and for a documented reason.

---

## 2. Module-Wide Design Rules

### 2.1 Prioritize meaningful data early

Users should see the most decision-relevant information in the first screenful.

Preferred order:

1. page identity
2. KPI summary or selection context
3. scope / filters
4. primary grid or primary workspace
5. supporting guidance and secondary insights

Avoid putting long instructional content before the main working data.

### 2.2 One screen, one primary job

Each page should have one dominant job:

- maintain setup
- browse a register
- review history
- run a controlled action
- inspect events

If a screen is doing more than one of those heavily, split the secondary responsibilities into:

- dialogs
- drawers
- tabs
- follow-on screens

### 2.3 One major grid per page

Each screen should generally have one primary table.

Avoid:

- two dense grids stacked with equal importance
- side-by-side grids
- grid plus another grid-like detail strip fighting for attention

Secondary information should be represented as:

- KPI cards
- mini-stat cards
- action cards
- row detail dialogs
- timeline/event cards

### 2.4 Decision-first layout

A screen should answer these questions quickly:

- what am I looking at
- what scope is active
- what requires my attention
- what can I do next

Anything that does not help answer those questions should appear later or be collapsed.

### 2.5 Consistent surface language

The whole Asset module should reuse the same visual grammar:

- rounded premium cards
- soft gradient surfaces
- compact but breathable toolbars
- KPI cards with clear value hierarchy
- mini-stat cards for supporting facts
- section leads for grouped decision context
- sticky footer or sticky header only when the workflow benefits

### 2.6 Dialog discipline

Dialogs should be used only when they improve focus.

Dialogs should:

- have a clear title and purpose line
- show enough context to support the decision inside the dialog
- blur and dim the background strongly enough to remove visual competition
- not require the user to keep referencing the page behind

### 2.7 Guidance should be secondary

Guidance, notes, and policy explanations should never push the main working data too low.

Preferred treatment:

- compact callouts
- lower secondary band
- dedicated info dialog
- section lead above an action area

### 2.8 Mobile and laptop discipline

All screens should remain usable on laptop widths first.

Priority breakpoints:

- desktop wide
- standard laptop
- tablet
- mobile

The module should not rely on ultra-wide layouts for clarity.

---

## 3. Shared UI Components To Repeat

These are the patterns every asset screen should reuse where relevant.

### 3.1 Hero header

Use when:

- the page is a major operating surface

Contains:

- eyebrow
- title
- short purpose sentence
- scope chips if useful

Examples:

- Asset Master
- Asset Settings
- Fixed Asset Register
- Depreciation Run

### 3.2 Scope card

Use when the page is driven by year/entity/subentity or report filters.

Contains:

- scope selectors
- search
- category/status filters if relevant
- primary refresh/apply action
- reset as secondary

### 3.3 KPI summary band

Use when the page has headline values worth seeing early.

Examples:

- register counts
- total gross block
- net book value
- event counts
- depreciation totals

### 3.4 Primary data card

The main table or working area should sit inside a single strong shell.

Contains:

- table header copy
- count / row control
- primary table
- pager

### 3.5 Secondary insights band

Use below the main work area for:

- runtime policy
- quick notes
- exceptions
- reminders

This is where non-primary but still useful content should go.

### 3.6 Focused action dialogs

Use when:

- an action is governed
- an action needs precheck
- the action should not compete with routine editing

Examples:

- lifecycle action center
- reversal dialogs
- traceability review

---

## 4. Screen Classification

The remaining asset screens fall into three buckets.

### 4.1 Setup screens

- Asset Settings
- Asset Category Master
- Asset Master

### 4.2 Register and report screens

- Fixed Asset Register
- Depreciation Schedule
- Asset Events
- Asset History

### 4.3 Operational screens

- Depreciation Run
- Asset Location / Custodian

Each bucket should share common structure.

---

## 5. Target Structure By Screen

## 5.1 Asset Master

Status:

- largely complete

Keep as reference baseline.

Final follow-up only:

- responsive QA
- focus-state QA
- visual consistency QA against other screens

## 5.2 Asset Category Master

Status:

- largely complete

Keep aligned to Asset Master patterns:

- focused popup workspace
- calm grid
- grouped setup sections
- sticky action footer

Follow-up only:

- responsive QA
- consistency pass against Asset Master spacing and card rhythm

## 5.3 Asset Settings

Primary job:

- manage scope-level defaults and policy rules

Target structure:

1. hero header
2. KPI/policy summary band
3. scope selector card
4. main settings workspace
5. secondary explanatory notes lower down

UI treatment:

- settings should not feel like one long raw form
- group into cards:
  - valuation defaults
  - posting policies
  - operational mandatory rules
  - traceability advisory rules
  - accounting readiness rules
- consider accordion or vertical section nav if length grows

Key rule:

- policies should be scannable before editable

## 5.4 Fixed Asset Register

Primary job:

- browse, review, and export asset register reporting

Target structure:

1. hero header
2. KPI summary band
3. compact scope/filter card
4. main register grid
5. export and drilldown actions
6. lower policy/help only if really needed

UI treatment:

- this screen should feel report-first
- no instructional content above the main register unless it is extremely compact
- prioritize:
  - asset code
  - asset name
  - category
  - status
  - acquisition / capitalization
  - gross block
  - accumulated depreciation
  - NBV

Likely dialogs:

- row detail
- drilldown to asset history

## 5.5 Depreciation Run

Primary job:

- prepare, review, and post depreciation runs

Target structure:

1. header
2. run summary KPIs
3. run parameter card
4. run results grid
5. precheck / warnings / posting action card
6. reversal/cancel area if needed

UI treatment:

- postable run totals should appear high
- the run result grid should dominate the page
- warnings and policy notes should support the decision, not bury the table

## 5.6 Asset History

Primary job:

- explain the lifecycle and journal story of one asset

Target structure:

1. selected asset context header
2. asset snapshot KPI band
3. timeline/event rail
4. journal/posting detail area

UI treatment:

- this screen should feel narrative and audit-friendly
- emphasize chronology
- reduce generic table feel where possible

## 5.7 Asset Events

Primary job:

- review lifecycle events across assets

Target structure:

1. header
2. event KPIs
3. filters
4. event grid
5. optional detail dialog

UI treatment:

- more operational monitoring than setup
- event type, status, posting state, and date should be immediately scannable

## 5.8 Asset Location / Custodian

Primary job:

- operational reassignment and tracking

Target structure:

1. header
2. assignment summary KPIs
3. scope/filter card
4. asset selection grid
5. focused reassignment workspace

UI treatment:

- this should feel like an operations workspace, not a report
- one selected-asset reassignment panel is better than crowding reassignment into each row

## 5.9 Depreciation Schedule

Primary job:

- view depreciation schedule detail

Target structure:

1. header
2. context and scope strip
3. totals summary band
4. schedule grid
5. export/drilldown

UI treatment:

- prioritize the schedule table
- guidance should be minimal

---

## 6. Design Translation Rules

When moving the master-screen design language onto another asset screen, apply these translations.

### 6.1 From “generic form” to “guided section”

Replace:

- long unbroken form

With:

- named section cards
- section purpose line
- grouped related fields

### 6.2 From “flat report” to “decision-ready report”

Replace:

- filters first, dense table second, no summary

With:

- short summary first
- compact scope next
- main table immediately after

### 6.3 From “all actions visible together” to “governed action zones”

Replace:

- many similar-looking action buttons

With:

- grouped action areas
- normal vs governed action separation
- dialogs for risky actions

### 6.4 From “background content stays loud” to “focused working surface”

Replace:

- visible distracting page content behind dialogs

With:

- strong mask
- blur
- proper modal focus

---

## 7. Delivery Sequence

Recommended next order from here:

1. Asset Settings
2. Fixed Asset Register
3. Depreciation Run
4. Asset History
5. Asset Events
6. Asset Location / Custodian
7. Depreciation Schedule

Reason:

- Asset Settings completes the setup family
- Fixed Asset Register completes the most-used report surface
- Depreciation Run completes the main controlled operational flow

---

## 8. Definition Of Done For Each Screen

A screen is only considered complete when all of the following are true:

### 8.1 Responsibility is clear

The page has one obvious primary job.

### 8.2 Meaningful data is visible early

The first screenful contains either:

- primary summary
- primary grid
- primary action context

not just helper text.

### 8.3 Layout feels related to Asset Master

The screen visibly belongs to the same module family.

### 8.4 No wasted vertical space

Guidance or secondary content does not push the main work area too low.

### 8.5 Actions are properly grouped

Routine actions and governed actions do not visually compete.

### 8.6 Dialogs are self-sufficient

If a dialog is opened, the user can decide from inside the dialog without relying on the page behind.

### 8.7 Responsive behavior is verified

At least:

- desktop
- standard laptop
- tablet

must be reviewed.

### 8.8 Type safety remains clean

Frontend verification should include:

- `npm run typecheck`
- focused component specs where relevant

---

## 9. Working Rule For Future Asset UI Changes

Any future asset UI change should answer these questions before implementation:

1. Is this primary or secondary information?
2. Does it belong on the page or in a dialog?
3. Does it help a decision, or is it only explanatory?
4. Will it push meaningful data too far down?
5. Does it match the Asset Master visual grammar?

If the answer set is unclear, the change should be reviewed before implementation.

---

## 10. Immediate Next Step

Use this plan as the rollout guide for the remaining screens.

The next screen to align to the master-screen design system should be:

1. `Asset Settings`, if we want to complete the setup family first

or

2. `Fixed Asset Register`, if we want the most visible reporting screen to catch up next

Both should use this plan as the design contract.
