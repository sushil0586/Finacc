# GST Reports Frontend Refactor Guide

Date: 2026-05-08

## Purpose

This guide is for future frontend developers who may need to clean up or split the GST report screens without changing business behavior.

This is not an urgent refactor document. It is a safe-maintenance guide for future work.

## Current Situation

The GST reports are working and are already reasonably usable, but the frontend implementation is not perfectly uniform.

Current realities:
- GSTR-1 has the heaviest custom UI logic
- GSTR-3B already follows a cleaner shell pattern
- GSTR-9 is closer to the newer reporting style

The biggest current engineering risk is not customer usability. It is long-term maintainability.

## Refactor Goals

If this area is refactored later, the goals should be:
- reduce duplicated report-shell logic
- standardize filters, loading states, export controls, and table wrappers
- keep statutory logic in services or view models where possible
- avoid changing user-facing workflows during technical cleanup

## Recommended Refactor Boundaries

### 1. Shared GST Filter Bar

Extract a shared component for:
- entity
- financial year
- date or period controls
- branch or subentity selection
- reload actions

### 2. Shared Report Header Actions

Extract shared actions for:
- export buttons
- validation button or toggle
- refresh
- snapshot or freeze actions where applicable

### 3. Shared Table Shell

Use one shared table shell for:
- loading state
- empty state
- error state
- sticky header or responsive grid behavior

### 4. Shared Validation Panel

GSTR-1 and GSTR-9 already expose validation-style output.

That output should eventually use:
- one warning list pattern
- one severity and code display pattern
- one empty-success state pattern

### 5. GSTR-1 Section Mapping Cleanup

GSTR-1 is the best candidate for targeted cleanup because it carries the most local mapping logic.

Good future extraction candidates:
- section registry or config map
- column definition builders
- section-specific summary cards
- invoice drilldown launcher

## What Should Stay in the Container

Keep these in the top-level container:
- route-level initialization
- final filter state ownership
- data fetch orchestration
- permission-aware UI state
- report-level export orchestration

## What Should Move Out

Move these into smaller reusable units when safe:
- filter bar rendering
- table shells
- validation display
- repeated button strips
- static column config

## Safe Extraction Order

If refactor work starts later, use this order:

1. shared styling tokens and wrappers
2. filter bar extraction
3. validation panel extraction
4. reusable table shell extraction
5. GSTR-1 section config cleanup

This sequence reduces visual drift first and business risk later.

## Guardrails

When refactoring:
- do not change report meaning
- do not rename routes without checking RBAC and menu dependencies
- do not change export request contracts casually
- do not move scope logic into presentation-only helpers
- keep entity and period behavior exactly stable unless fixing a known bug

## Minimum Smoke Tests After Refactor

After any future cleanup, manually test:
- `gstreport`
- `gstr3breport`
- `gstr9report`

For each screen, verify:
- access still works
- filters still work
- summary loads
- drilldown loads
- export still works
- validation or warnings still render

## Recommendation

Do not refactor GST Reports only for code neatness if the customer is happy and the screens are stable.

Refactor later only when:
- new statutory changes are expected
- multiple developers are actively changing the area
- merge conflicts or regressions become frequent
- visual consistency across report modules becomes a priority
