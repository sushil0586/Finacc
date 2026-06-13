# Invoice Performance Implementation Plan

Status: planning only. No code changes applied.

Date: 2026-06-13

Related review:
- [invoice-performance-audit.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-audit.md:1)

## Objective

Improve sales and purchase invoice performance with low-risk, phase-wise work.

Primary goals:
- reduce unnecessary network payload
- reduce repeated metadata requests
- improve perceived screen responsiveness
- avoid risky schema changes unless proven necessary

Non-goals for the first phases:
- changing invoice numbering from `int` to `bigint`
- redesigning invoice business logic
- changing accounting/posting rules

## Working Principle

Do the safest, highest-signal work first:

1. measure
2. narrow repeated API usage
3. split heavy metadata into smaller refresh endpoints
4. optimize detail payloads only if profiling proves they are still the bottleneck
5. revisit schema only if real data volume requires it

## Phase 0: Baseline And Instrumentation

Goal:
- establish current performance baselines before changing behavior

Why this phase first:
- prevents “optimization by guesswork”
- lets us prove impact of each later phase

Scope:
- sales invoice create screen load
- sales invoice existing invoice load
- purchase invoice create screen load
- purchase invoice existing invoice load
- customer/vendor refresh after popup save
- product refresh after popup save
- branch change flow

Deliverables:
- browser network waterfall snapshots
- API payload sizes for:
  - sales form meta
  - sales line meta
  - purchase form meta
  - purchase line meta
  - sales detail meta
  - purchase detail meta
- backend timing notes for these endpoints
- SQL query counts for invoice detail endpoints in debug/local environment

Suggested measurements:
- total API calls per screen load
- total transferred KB/MB per screen load
- largest 3 endpoints by payload
- average time for branch switch
- average time for customer/vendor refresh

Risk:
- very low

Expected impact:
- no user-visible speedup yet
- high confidence for all next phases

Exit criteria:
- baseline numbers are documented
- top 3 hotspots are confirmed with data, not assumptions

## Phase 1: Frontend Refresh Narrowing

Goal:
- stop using full metadata endpoints for small refresh actions

Highest-priority targets from the audit:
- sales customer refresh currently reloads full form meta
- purchase vendor refresh currently reloads full form meta
- sales product refresh reloads full line meta
- purchase product refresh patterns should be reviewed similarly

Planned changes:
- create narrow refresh flows for:
  - customer list only
  - vendor list only
  - product list only
  - optionally charge types only if needed
- update popup-close behavior to refresh only the changed list

Likely backend work:
- add smaller endpoints or narrower query modes for:
  - sales customers
  - purchase vendors
  - sales products
  - purchase products

Likely frontend work:
- replace broad `getSalesInvoiceFormMeta(...)` refresh usage in customer popup flows
- replace broad `getPurchaseInvoiceFormMeta(...)` refresh usage in vendor popup flows
- replace full line-meta refresh where only product list changed

Risk:
- low to medium

Main watchouts:
- keep existing display fields intact
- preserve backward compatibility for forms expecting current list shape
- ensure newly created customer/vendor/product appears immediately after save

Expected impact:
- good improvement on popup workflows
- noticeable reduction in repeated payload transfer

Exit criteria:
- customer refresh no longer triggers full sales form meta
- vendor refresh no longer triggers full purchase form meta
- product refresh no longer requires full line meta unless truly necessary

## Phase 2: Screen Bootstrap Caching

Goal:
- reduce repeated bootstrap calls during the same session/scope

Problem addressed:
- branch change and master-data bootstraps reload large payloads repeatedly

Planned changes:
- add client-side caching by `(entity, entityFinId, subentity, lineMode)` for:
  - form meta
  - line meta
  - settings
- add explicit cache invalidation rules when:
  - branch changes
  - user creates a new customer/vendor/product
  - settings-affecting actions occur

Recommended approach:
- keep caches in facade/service layer instead of component-only state where practical
- allow “force refresh” for admin/mutation flows

Risk:
- medium

Main watchouts:
- stale dropdown lists
- stale numbering/settings after branch change
- cache invalidation mistakes causing confusing UI state

Expected impact:
- better perceived responsiveness
- fewer repeat calls during same work session

Exit criteria:
- repeated visits to invoice screens reuse cached stable metadata
- branch-change behavior remains correct
- force-refresh paths still work after popup mutations

## Phase 3: Metadata Endpoint Decomposition

Goal:
- split heavy “all-in-one” meta responses into purposeful modules

Why this phase comes after Phase 1 and 2:
- first remove obvious waste
- then refactor endpoint contracts where payload is still too large

Potential decomposition:

Sales:
- scope meta
  - financial years
  - subentities
- party meta
  - customers
- line meta
  - products
  - UOMs
  - tax defaults
- settings meta
  - numbering
  - seller defaults
  - compliance defaults
- statutory meta
  - TCS sections

Purchase:
- scope meta
  - financial years
  - subentities
- party meta
  - vendors
- line meta
  - products
  - purchase behaviors
- settings meta
  - numbering
  - withholding defaults
- statutory meta
  - TDS sections

Risk:
- medium to high

Main watchouts:
- frontend contract churn
- duplicate migration logic in components
- accidental mismatch between create mode and edit mode payloads

Expected impact:
- large reduction in payload size
- easier long-term maintenance

Exit criteria:
- invoice screens no longer depend on one oversized meta payload
- contracts are documented and stable

## Phase 4: Detail Endpoint Payload Optimization

Goal:
- optimize existing invoice edit/detail responses if still needed after earlier phases

Important note:
- this phase should happen only after measuring post-Phase 1 to 3 results

Possible work:
- review whether all nested fields in invoice detail/edit payload are needed at first render
- defer non-critical blocks:
  - navigation hints
  - compliance artifacts
  - history/event blocks
  - attachments
  - derived summary panels
- load optional panels lazily when user opens them

Risk:
- medium

Main watchouts:
- edit form regressions
- extra spinner/loading behavior
- fragmented UI state if lazy loading is poorly sequenced

Expected impact:
- improved initial invoice-open latency
- especially useful on large invoices with many lines

Exit criteria:
- invoice detail payload is trimmed or modularized
- opening an invoice is measurably faster than baseline

## Phase 5: Query-Level Backend Review

Goal:
- fine-tune Django ORM only where data proves it matters

Areas to review:
- invoice meta queries with large customer/vendor/product sets
- detail-form endpoints that may overlap with settings/meta data
- any duplicate queries caused by serializers or computed fields

Likely techniques:
- `.only(...)`
- `.values(...)`
- targeted `Prefetch(...)`
- remove serializer-driven N+1 behavior if present
- optional pagination or typeahead for very large customer/vendor/product masters

Important note:
- list and detail invoice endpoints are already fairly disciplined in several places
- this phase should focus on proven hotspots, not broad rewrites

Risk:
- medium

Expected impact:
- moderate but meaningful backend efficiency gains

Exit criteria:
- top measured expensive ORM paths are reduced
- no correctness regressions in invoice create/edit flows

## Phase 6: Large Master Data Strategy

Goal:
- keep invoice screens responsive for large entities

Problem this phase solves:
- even well-optimized endpoints can become heavy if they return thousands of customers, vendors, or products

Potential solutions:
- server-side search/typeahead for products
- server-side search/typeahead for customers/vendors
- incremental dropdown loading
- background prefetch after initial screen render

Risk:
- medium to high

Expected impact:
- high for large datasets
- minimal for small datasets

Exit criteria:
- invoice screens stay responsive even with large master lists

## Phase 7: Schema Review Only If Needed

Goal:
- revisit schema choices only after real evidence

Current recommendation:
- do not change `doc_no` from `PositiveIntegerField` yet

When to reopen this:
- if document numbering can exceed 32-bit positive range
- if imported legacy numbers already exceed that range
- if a business-wide numbering strategy demands it

Why this phase is last:
- likely low ROI today
- adds migration cost and testing burden
- does not address the current dominant performance risks

Risk:
- high relative to expected benefit

Expected impact:
- little to no performance gain by itself

Exit criteria:
- only proceed with data-backed justification

## Recommended Execution Order

Recommended sequence:

1. Phase 0
2. Phase 1
3. Phase 2
4. Re-measure
5. Phase 3
6. Re-measure
7. Phase 4 and Phase 5 as needed
8. Phase 6 only if large-data behavior still hurts
9. Phase 7 only if numbering scale requires it

## Suggested Sprint Packaging

### Sprint A
- Phase 0
- Phase 1

Expected result:
- fastest low-risk win

### Sprint B
- Phase 2
- post-change measurement

Expected result:
- smoother repeated invoice work in same session

### Sprint C
- Phase 3
- partial Phase 4 if needed

Expected result:
- cleaner API contracts and smaller bootstrap payloads

### Sprint D
- Phase 5
- Phase 6 for large datasets if needed

Expected result:
- targeted deeper optimization where measurements justify it

## Acceptance Metrics

Use these target metrics to judge success:

- reduce invoice create-screen API payload by 30% or more
- reduce popup refresh calls from full-meta payloads to targeted payloads
- reduce branch-switch wait time noticeably
- reduce invoice screen boot API count where safe
- preserve existing invoice save correctness and compliance behavior

## Proposed First Implementation Slice

If work begins, start here:

1. Measure current sales and purchase invoice screen payloads
2. Implement customer-only refresh on sales invoice
3. Implement vendor-only refresh on purchase invoice
4. Re-measure
5. Decide whether product-only refresh should be next or whether caching brings more value first

Reason:
- narrow scope
- low regression risk
- easy to validate
- likely immediate improvement
