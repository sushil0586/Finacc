  # Purchase Statutory Frontend Refactor Guide

Date: 2026-05-08

## Purpose

This document is an internal engineering guide for future frontend refactoring of the Purchase Statutory screen.

The goal is not to redesign the screen.

The goal is to make future development safer by breaking the current large component into smaller, easier-to-maintain pieces without changing the business experience that users already like.

## Current Situation

Current frontend files:
- `purchase-statutory.component.ts`
- `purchase-statutory.component.html`
- `purchase-statutory.component.scss`

Current size:
- TypeScript: about 4430 lines
- HTML: about 1880 lines
- SCSS: about 865 lines

This means the screen is functionally rich, but high-risk for future changes because:
- one file owns too many workflows
- state is shared across unrelated sections
- UI changes can accidentally affect another section
- onboarding new developers takes longer
- testing changes becomes harder

## Important Principle

Do not refactor this screen only for code cleanliness.

Refactor it only when:
- new statutory features are still being added
- multiple developers need to work on it
- bugs are becoming difficult to isolate
- merge conflicts are increasing
- release confidence is dropping because one change touches too much code

If the customer is happy and the screen is stable, this document should be treated as a future-safe blueprint, not an immediate action item.

## Current Functional Areas

The screen already has natural business boundaries.

These are the best future split points:

1. Overview
- summary cards
- status hints
- guidance text

2. GSTR-2B
- import batch
- batch rows
- auto match
- row review
- CSV upload/download helpers

3. Reconciliation
- reconciliation exception grid
- GL reconciliation grid
- reasoning / guidance display

4. ITC Register
- ITC grid
- ITC review popup
- claim / block / unblock / review actions

5. Challan Operations
- challan list/grid
- challan create/edit
- one-click/auto-fill flows
- deposit flow
- approval/cancel/delete actions
- challan export helpers

6. Return Operations
- return list/grid
- return create/edit
- eligible-line population
- filing flow
- approval/cancel/delete actions
- NSDL export
- return filing pack export

7. Form 16A and Evidence
- Form 16A issue list
- official upload
- certificate download

8. Shared Workflow Dialogs
- approval dialog
- cancel dialog
- delete dialog
- remarks-driven action modal

## Recommended Future Component Structure

Keep one thin container component and move feature blocks into focused child components.

Suggested structure:

```text
purchase-statutory/
  purchase-statutory.component.ts              # container/orchestrator only
  purchase-statutory.component.html
  purchase-statutory.component.scss

  components/
    statutory-overview/
    statutory-gstr2b-panel/
    statutory-reconciliation-panel/
    statutory-itc-register-panel/
    statutory-challan-panel/
    statutory-return-panel/
    statutory-form16a-panel/
    statutory-workflow-dialog/
    statutory-guidance-banner/

  models/
    statutory-ui-state.ts
    statutory-draft-models.ts

  utils/
    statutory-formatters.ts
    statutory-csv.util.ts
    statutory-filter.util.ts
    statutory-download.util.ts
```

## What Should Stay In The Container

The top-level container should keep only:
- current entity / financial year / subentity context
- top-level date and tax-type filters
- section switching
- page-level loading state
- calls that refresh the whole workspace
- shared notification handling

The container should not keep detailed draft form logic for every feature forever.

## What Should Move Out First

The safest first moves are utility and presentational moves, not workflow rewrites.

### Phase 1. Extract Pure Utilities

Move these first:
- CSV parsing helpers
- formatting helpers
- approval-state label helpers
- file download helpers
- row normalization helpers
- sort/filter helper functions

This is low-risk because it does not change screen ownership much.

### Phase 2. Extract Small Presentational Blocks

Best early candidates:
- overview cards
- guidance / hint block
- reconciliation tables
- ITC review dialog

These usually need fewer side effects than the challan/return workflows.

### Phase 3. Extract GSTR-2B Panel

This is a strong candidate because it already has a clear mini-workflow:
- batch import
- row list
- auto match
- review popup

It can become one feature component with limited shared dependencies.

### Phase 4. Extract Challan Panel

Move together:
- challan grid
- challan draft form
- deposit popup
- challan actions

Do not split challan list and challan editor too early unless state is already stabilized.

### Phase 5. Extract Return Panel

Move together:
- return grid
- return draft form
- filing logic
- return actions
- exports

Return logic is closely linked to challan usage and should be refactored after challan patterns are proven.

### Phase 6. Extract Form 16A Panel

This can either stay under the return panel or become its own small feature block depending on future growth.

## Shared State Strategy

One of the biggest risks is moving UI blocks without a state plan.

Recommended rule:
- keep server-canonical state in the container
- keep temporary form state in the child feature component
- emit completed actions upward
- refresh canonical data from the container after save/update/delete actions

Avoid:
- deep child-to-child communication
- hidden coupling through template references
- children mutating each other’s arrays directly

## Suggested Input/Output Pattern

Each feature component should receive only the data it needs.

Example pattern:

```text
Container
  -> inputs: scope, data, meta, loading flags
  <- outputs: refresh, create, update, delete, approve, cancel, export
```

This keeps the child components reusable and easier to test.

## Refactor Rules

When refactoring this screen in future, follow these rules:

1. Do not change business wording and flow unless there is a product decision.
2. Do not mix visual redesign with structural refactor in the same pass.
3. Move one business area at a time.
4. Keep API service contracts unchanged during the first refactor pass.
5. After each extraction, run a manual smoke test for the whole screen.
6. Prefer small commits per extracted feature area.

## Minimum Manual Smoke Test After Every Refactor Slice

After any extraction, test at least:
- screen opens
- scope filters apply correctly
- overview loads
- GSTR-2B batch list still opens
- challan grid still loads
- return grid still loads
- one modal action still works
- exports still trigger

If the extracted slice is workflow-specific, test that workflow end to end.

## Recommended Refactor Order

Best future order:

1. Extract utilities
2. Extract overview and guidance
3. Extract reconciliation
4. Extract ITC review dialog
5. Extract GSTR-2B panel
6. Extract challan panel
7. Extract return panel
8. Extract Form 16A area
9. Reduce container state and dead code

This order lowers risk and gives early maintainability gains without touching the most complex areas first.

## What Not To Do

Avoid these mistakes:

- splitting the file into many tiny components with unclear ownership
- moving code without reducing coupling
- changing data shape while also splitting UI
- renaming too many methods at once
- refactoring challan and return workflows together in one giant change
- redesigning CSS structure and logic structure in the same release

## Suggested Future Deliverables

When this refactor is actually taken up, the work should ideally produce:
- smaller standalone child components
- extracted UI utility helpers
- reduced component state size
- better section-level tests
- an updated README for the statutory frontend structure

## Final Recommendation

This refactor is useful, but not urgent if:
- customer satisfaction is high
- bugs are under control
- only small changes are expected

It becomes worth doing when development speed, confidence, or maintainability starts to drop.

Until then, this document should be used as the safe blueprint for future engineering work.
