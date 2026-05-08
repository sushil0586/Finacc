# TCS Frontend Refactor Guide

Date: 2026-05-08

## Purpose

This document is an internal engineering guide for future frontend refactoring of the TCS screens.

The goal is not to redesign the module.

The goal is to make future development safer if the TCS area grows further and we need to break the screens into smaller, easier-to-maintain units.

## Current Situation

The TCS frontend is more manageable than the Purchase Statutory screen, but it still spans multiple operational pages with rich workflow behavior:

- `tcs-sections`
- `tcs-config`
- `tcs-party-profiles`
- `tcs-statutory`
- `tcs-return-27eq`

The biggest long-term maintenance risk is not one massive single file.

It is that the operational workflow is spread across multiple screens, each with filters, exports, modals, and state-heavy UI logic.

## Important Principle

Do not refactor these screens just for code cleanliness.

Refactor only when one of these becomes true:
- multiple developers are editing the same screen family often
- modal and grid changes are causing regressions
- shared UI logic is duplicated too much
- state handling becomes difficult to reason about
- testing confidence drops after normal UI changes

If users are happy and the module is stable, this document should be treated as a future-safe blueprint.

## Best Future Split Points

### 1. Shared TCS Shell

Keep all TCS pages visually and structurally aligned through a shared shell layer.

This should own:
- page wrapper
- card shell
- toolbar spacing
- button treatment
- dialog chrome
- table wrapper behavior

This has already started through the shared TCS shell stylesheet.

### 2. TCS Sections

Natural split points:
- list/grid area
- add/edit modal
- policy audit modal
- bulk import/export helpers

### 3. TCS Config

Natural split points:
- config list
- posting map list
- config modal
- posting map modal

### 4. TCS Party Profiles

Natural split points:
- profile list/grid
- profile form dialog
- branch filter toolbar

### 5. TCS Statutory Workspace

This is the highest-value future refactor candidate.

Natural split points:
- header/filter bar
- summary tile strip
- quality/operational guidance panel
- section summary panel
- workspace table
- collection dialog
- deposit dialog
- allocation dialog

### 6. TCS Return 27EQ

Natural split points:
- period/filter header
- filing-pack readiness block
- CA review block
- return list/grid
- return dialog

## Suggested Future Structure

```text
statutory/
  shared/
    tcs-shell.scss
    tcs-ui.models.ts
    tcs-formatters.ts
    tcs-export.util.ts

  tcs-statutory/
    tcs-statutory.component.ts        # container only
    components/
      tcs-workspace-header/
      tcs-workspace-metrics/
      tcs-workspace-flags/
      tcs-workspace-grid/
      tcs-collection-dialog/
      tcs-deposit-dialog/
      tcs-allocation-dialog/

  tcs-return-27eq/
    tcs-return-27eq.component.ts      # container only
    components/
      tcs-return-header/
      tcs-filing-pack-summary/
      tcs-ca-review-panel/
      tcs-return-grid/
      tcs-return-dialog/
```

## What Should Stay In Container Components

Keep only the following in top-level containers:
- current entity / FY / quarter context
- screen-level loading state
- top-level refresh actions
- API orchestration
- final notification handling

Do not keep every temporary form field and every grid helper forever in the container.

## Safest Refactor Order

### Phase 1. Extract Pure Utilities

Move first:
- export helpers
- formatting helpers
- status label helpers
- reusable filter helpers

Low risk, high clarity.

### Phase 2. Extract Presentational Panels

Best candidates:
- metrics strips
- readiness cards
- quality chip panels
- review summaries

These are easy wins because they usually have fewer side effects.

### Phase 3. Extract Dialog Components

Best candidates:
- collection dialog
- deposit dialog
- config dialog
- party profile dialog

Dialogs are often easier to isolate than grid orchestration.

### Phase 4. Extract Grid Components

Move:
- workspace grid
- return grid
- posting map grid

Do this after shared action patterns are stable.

### Phase 5. Extract Full Workflow Panels

Only after earlier phases are stable:
- TCS workspace feature shell
- Return 27EQ feature shell

## Shared State Strategy

Recommended rule:
- keep server-canonical state in the container
- keep temporary dialog form state inside the dialog component
- emit completed save/update/delete actions upward
- refresh canonical data after a successful workflow action

Avoid:
- child-to-child hidden communication
- duplicated filter state across components
- mixing export concerns into every dialog

## Refactor Guardrails

If future refactoring begins, keep these rules:

- do not change route names unless necessary
- do not redesign the business flow while splitting components
- keep API contracts unchanged during UI-only refactor phases
- preserve current permission behavior
- preserve current export entry points

## Minimum Smoke Test After Any Refactor

After each refactor phase, test:

1. Open every TCS page.
2. Open every main dialog.
3. Change FY/quarter filters.
4. Run at least one export from workspace or return screen.
5. Create one safe test collection or deposit if environment allows.
6. Confirm no layout regression on table-heavy pages.
7. Confirm mobile or narrow-width wrapping still works.

## Recommendation

There is no urgent need to refactor this frontend now.

The customer is already happy, and the recent shell-alignment pass improved consistency.

Treat this guide as a future engineering plan, not an immediate delivery item.

