# Finacc Stress Testing Master Plan

Last updated: 2026-08-03

## Purpose

This document is the master execution runbook for Finacc product stress testing.

It is designed to answer five practical questions:

1. What exactly are we going to stress test?
2. In what order will we run it?
3. What counts as pass, fail, or partial success?
4. What evidence do we need to collect in each phase?
5. How will we update status after each completed phase?

This is not only a load-testing plan.

It combines:

- backend API stress
- database stress
- browser workflow stress
- concurrent mutation testing
- reporting and export load
- onboarding and new-entity bootstrap stress
- operator and end-user resilience validation

---

## How To Use This Document

Use this document as the single source of truth for:

- phase planning
- execution tracking
- bug logging handoff
- go / no-go conversations
- production hardening review

After each phase:

- update the `Phase Status` table
- update the `Execution Notes` section for that phase
- attach summary metrics
- list discovered defects
- mark whether rerun is required

Phase-specific execution runbooks:

- [finacc-stress-phase1-write-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-write-plan-2026-08-01.md:1)
- [finacc-next-hardening-plan-2026-08-03.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-next-hardening-plan-2026-08-03.md:1)
- [finacc-saas-1000-user-readiness-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-saas-1000-user-readiness-plan-2026-08-01.md:1)

---

## Scope

The stress program covers the full product in practical production-like layers:

1. Authentication and session flows
2. Entity and onboarding flows
3. Master and dropdown-heavy operational flows
4. Sales, purchase, payment, receipt, voucher mutation flows
5. Reports, filters, drilldowns, and exports
6. Inventory and manufacturing operational/reporting paths
7. Subscription and access-control behavior under active use
8. Mixed concurrency and multi-tab conflicts

---

## Objectives

The target is not only to measure speed.

The target is to validate:

- correctness under load
- stability under concurrency
- graceful degradation under pressure
- absence of data corruption
- absence of duplicate or lost mutations
- clear user-facing behavior during slow or conflicting operations

---

## Success Criteria

The product stress test is considered successful only if all of the following hold:

- no data corruption
- no orphaned or duplicate voucher creation
- no broken links between invoices, notes, allocations, or settlements
- no silent UI breakage during slow or repeated operations
- acceptable response time at expected working load
- acceptable error rate at expected working load
- controlled and diagnosable degradation at peak load
- no uncontrolled memory, CPU, or DB connection leak
- system recovers after pressure is removed

---

## Proposed SLA Baseline

These are the initial target thresholds for a healthy environment.

- login: `p95 < 2s`
- entity switch: `p95 < 2s`
- dropdown search/meta load: `p95 < 1.5s`
- invoice draft save: `p95 < 3s`
- invoice post: `p95 < 5s`
- payment/receipt save: `p95 < 4s`
- report refresh: `p95 < 8s`
- export generation trigger: `p95 < 5s`
- export completion: `p95 < 20s`
- new entity creation: `p95 < 10s`

These values can be tightened after the first baseline run.

---

## Test Environment Requirements

Before running any phase, confirm the following:

- backend version frozen for the run
- frontend version frozen for the run
- database snapshot known
- monitoring enabled
- seed data known and documented
- background workers stable
- export/storage dependencies stable
- no unrelated admin debugging changes in active environment

Environment options:

- local performance clone
- staging clone
- dedicated performance environment

Preferred order:

1. local baseline
2. staging-like environment
3. controlled production-like simulation

---

## Monitoring Requirements

Collect all of the following during every phase:

- API response times
- p50, p95, p99 latency
- error rate
- timeout rate
- backend CPU
- backend RAM
- DB CPU
- DB RAM
- DB connections
- slow queries
- queue or background worker backlog
- frontend console errors
- frontend failed network calls

If possible, also collect:

- request-per-endpoint distribution
- query count per hot route
- export job duration histogram
- retry count for failed requests

---

## Load Levels

Each phase should be run in increasing depth.

### Level 0: Smoke

- `5` concurrent users
- `10` minutes
- goal: basic stability

### Level 1: Working Load

- `20` concurrent users
- `20` minutes
- goal: simulate ordinary business-day activity

### Level 2: Peak Load

- `50` concurrent users
- `30` minutes
- goal: validate busy-hour resilience

### Level 3: Stress Load

- `100` concurrent users
- until threshold degradation
- goal: locate non-linear slowdown and failure behavior

### Level 4: Breakpoint

- ramp above `100`
- goal: find exact breaking point and recovery behavior

---

## Workload Families

### 1. Authentication And Session

- login
- logout
- token refresh
- entity switch
- restore session after idle
- same user across multiple tabs

### 2. Onboarding And Entity Bootstrap

- new user registration
- new entity creation for existing user
- default accounts bootstrap
- default settings bootstrap
- feature access hydration
- post-onboarding first-use workflow

### 3. Master And Dropdown Stress

- customer search
- vendor search
- product search
- ledger search
- account search
- branch/subentity selector load
- financial year selector load
- report filters with large option sets

### 4. Transaction Mutation Stress

- sales invoice create/save/post/unpost
- purchase invoice create/save/post/unpost
- debit note / credit note flows
- payment save/submit/approve/reject
- receipt save/submit/approve/reject
- journal and voucher mutation flows
- linked-reference mutation flows

### 5. Reporting Stress

- trial balance
- balance sheet
- profit and loss
- trading account
- ledger book
- ledger summary
- cashbook
- daybook
- payables reports
- receivables reports
- inventory reports
- compliance reports
- export pdf/excel/csv

### 6. Concurrency Conflict Stress

- same voucher in two tabs
- stale approval state
- save/post races
- save/unpost races
- note/reference relink conflicts
- report refresh while posting is active

### 7. Mixed Production-Like Activity

- users creating invoices
- other users running reports
- some users exporting
- some users approving payments
- some users switching entities
- some users onboarding new entities

---

## Phase Plan

## Phase 0: Baseline And Instrumentation

### Goal

Establish a reliable baseline before heavy stress begins.

### Current Local Baseline Assumptions

These assumptions are confirmed or inferred from the current working setup as of `2026-08-01`:

- backend is expected on `http://127.0.0.1:8000`
- frontend is expected on `http://127.0.0.1:4200`
- backend root HTTP probe currently responds from local Django server
- frontend should be validated through browser/runtime flow, not only `HEAD` probes
- primary execution mode for Phase 0 should start on local environment

### Existing Tooling Already Present In Repo

The repository already contains a reusable API-load baseline setup:

- Locust directory:
  - [Finacc/perf/locust](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust)
- existing runner:
  - [locustfile.py](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/locustfile.py)
- execution guidance:
  - [README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md)
- existing result artifacts already in repo:
  - read-only result sets
  - lifecycle result sets
  - purchase modern and legacy result sets
  - 50-user result artifacts

This means Phase 0 does not need fresh tooling design before execution.

### Activities

- freeze test build
- validate monitoring
- validate logging
- confirm seed data
- confirm hot endpoints
- record current latency without stress

### Deliverables

- baseline response-time snapshot
- environment checklist
- hot-route list
- known-risk list before load

### Phase 0 Initial Environment Checklist

Mark each item before first live run:

- backend running on `8000`
- frontend running on `4200`
- test user credentials confirmed
- test entity, entity financial year, and subentity confirmed
- seed data shape known
- logging enabled for backend errors
- DB visibility available
- browser console/network capture available
- Locust environment file prepared
- safe environment decision recorded for write scenarios

### Phase 0 Hot Route Shortlist

The first baseline should watch these routes before expanding:

#### Authentication and session

- `/api/auth/login`
- `/api/auth/me`

#### Dashboard and meta

- `/api/dashboard/home/meta/`
- `/api/reports/payables/meta/`
- `/api/bank-reconciliation/meta/`
- `/api/bank-reconciliation/sessions/`

#### Sales operational

- `/api/sales/invoices/`
- `/api/sales/invoices/lookup/`
- `/api/sales/service-invoices/lookup/`
- `/api/sales/invoices/<id>/cross-mode-nav/`
- `/api/sales/service-invoices/<id>/cross-mode-nav/`
- `/api/sales/settings/`

#### Purchase operational

- `/api/purchase/purchase-invoices/lookup/`
- `/api/purchase/purchase-service-invoices/lookup/`
- `/api/purchase/purchase-invoices/<id>/cross-mode-nav/`
- `/api/purchase/purchase-service-invoices/<id>/cross-mode-nav/`

#### Payments and vouchers

- `/api/payments/payment-vouchers/`
- `/api/payments/meta/voucher-form/`
- `/api/vouchers/vouchers/`
- `/api/vouchers/meta/voucher-form/`

#### Onboarding and subscription

- `/api/subscriptions/public/plans`
- onboarding and entity creation APIs used by the frontend flow

#### Reporting and export

- financial report run endpoints
- payables aging
- ledger and statement report endpoints
- export endpoints for PDF, Excel, and CSV on key reports

### Phase 0 Initial Known Risks

Before any stress run, assume these risk areas need explicit observation:

- dropdown/meta endpoints can appear healthy at API level while failing UI hydration
- read-heavy report routes may remain correct but degrade in latency under larger masters
- new-entity defaults can hide bootstrap problems until first operational use
- cross-mode navigation and lookup routes are high-value because many invoice/note screens depend on them
- browser-visible slowness may not align with pure API latency if client rehydration is heavy

### Exit Criteria

- environment stable
- instrumentation working
- seed and route list approved

---

## Phase 1: Read-Heavy Stress

### Goal

Stress read paths before mutation paths.

### Included flows

- login
- dashboard/meta
- dropdown searches
- entity switch
- financial year/subentity filters
- report refresh and filter runs

### Focus risks

- selector hydration mismatch
- slow report filters
- slow dropdowns
- route rehydration inconsistency
- cache or meta endpoint bottlenecks

### Exit Criteria

- stable working load on read flows
- no major selector or rehydration regressions
- report refresh within acceptable threshold

---

## Phase 2: Transaction Mutation Stress

### Goal

Stress operational mutation flows under realistic concurrency.

### Included flows

- sales invoice
- purchase invoice
- payment
- receipt
- debit/credit notes
- voucher save/post/unpost

### Focus risks

- duplicate records
- lost saves
- broken posting state
- stale action conflicts
- linked reference mismatches
- confirm/save/post UX inconsistency under load

### Exit Criteria

- no corruption
- no duplicate vouchers
- conflict behavior understandable and recoverable

---

## Phase 3: Reporting And Export Stress

### Goal

Validate heavy reporting and export behavior during active product usage.

### Included flows

- all main financial reports
- payables/receivables reports
- inventory and manufacturing reports
- compliance reports
- export pdf
- export excel
- export csv

### Focus risks

- slow queries
- export timeouts
- large result-set instability
- filter state mismatch
- drilldown correctness degradation

### Exit Criteria

- reports stable at working and peak load
- export operations remain controlled
- no correctness drift after concurrent mutations

---

## Phase 4: Onboarding, Access, And Bootstrap Stress

### Goal

Validate product behavior for fresh users and fresh entities under live pressure.

### Included flows

- new registration
- new entity creation
- default account setup
- default settings setup
- feature access hydration
- first invoice/report run after onboarding

### Focus risks

- missing defaults
- access denied unexpectedly
- role/subscription gating regressions
- empty dropdowns on fresh entity
- broken first-use path

### Exit Criteria

- fresh entity is operational without manual rescue
- no access-control surprise on default configuration
- first-use flows are stable and understandable

---

## Phase 5: Mixed Concurrency And Breakpoint Testing

### Goal

Run the product as it behaves in the real world, with mixed usage at once.

### Included flows

- concurrent operational mutation
- concurrent reports
- concurrent exports
- multi-tab workflows
- onboarding in parallel with active business usage

### Focus risks

- system-wide contention
- DB bottlenecks
- queue backlog
- user-facing race conditions
- partial saves and stale UI

### Exit Criteria

- breakpoint identified
- degradation pattern documented
- recovery behavior documented
- top bottlenecks prioritized

---

## Module-Wise Stress Matrix

| Module | Read Stress | Mutation Stress | Export Stress | Concurrency Stress | Fresh Entity Stress |
|---|---|---:|---:|---:|---:|
| Authentication | Yes | No | No | Yes | Yes |
| Entity / Onboarding | Yes | Yes | No | Yes | Yes |
| Sales | Yes | Yes | Yes | Yes | Yes |
| Purchase | Yes | Yes | Yes | Yes | Yes |
| Payment | Yes | Yes | Limited | Yes | Yes |
| Receipt | Yes | Yes | Limited | Yes | Yes |
| Notes | Yes | Yes | Limited | Yes | Yes |
| Financial Reports | Yes | No | Yes | Yes | Yes |
| Payables / Receivables Reports | Yes | No | Yes | Yes | Yes |
| Inventory Reports | Yes | Limited | Yes | Yes | Yes |
| Manufacturing Reports | Yes | Limited | Yes | Yes | Yes |
| Compliance Reports | Yes | Limited | Yes | Yes | Yes |
| Subscription / Access | Yes | Yes | No | Yes | Yes |

---

## Tooling Plan

### API Stress

Preferred tools:

- `k6`
- `Locust`

Use for:

- login
- meta
- reports
- invoice save/post APIs
- onboarding APIs

### Browser Stress

Preferred tool:

- Playwright

Use for:

- multi-user UI concurrency
- dropdown-heavy workflows
- mutation flows with real browser behavior
- multi-tab conflict flows
- screenshot capture on failures

### DB And Server Analysis

Use:

- slow query logs
- DB connection metrics
- app server CPU/RAM
- job queue monitoring

---

## Data Strategy

Stress testing is only useful if the data shape is realistic.

We should seed:

- large customer/vendor masters
- large product catalog
- many ledgers/accounts
- multiple branches/subentities
- realistic vouchers across periods
- linked notes and allocations
- partially settled payables/receivables
- report-heavy historical data

Data layers:

1. clean small seed
2. medium operational seed
3. large stress seed

---

## Evidence To Capture

For each phase collect:

- run date and environment
- commit/build version
- scenario list executed
- concurrency level
- duration
- p50/p95/p99 metrics
- errors
- screenshots for browser failures
- backend stack traces
- slow query extracts
- whether data was correct after the run

---

## Defect Logging Rules

Every defect should be tagged with:

- phase
- module
- workload type
- reproducibility
- severity
- correctness impact
- performance impact
- UX impact
- whether rerun is blocked

Severity guideline:

- `P0`: corruption, duplicate mutation, unrecoverable failure
- `P1`: major workflow break under normal stress
- `P2`: degraded but recoverable, incorrect UX behavior
- `P3`: tuning/clarity issue, no correctness loss

---

## Phase Status

| Phase | Name | Status | Owner | Last Run | Result | Rerun Needed | Notes |
|---|---|---|---|---|---|---|---|
| 0 | Baseline And Instrumentation | In Progress | Codex + User | 2026-08-01 | Smoke read-only, modern-read, post-fix read baselines, plus 10-user, 15-user, and 20-user modern working-load probes completed; zero failures across all probes; 20 users is the clear local saturation point | Yes | `sales/invoices [list]` improved sharply at smoke load, but purchase and sales cross-mode navigation plus heavier lookup/report routes still define the local ceiling |
| 1 | Read-Heavy Stress | In Progress | Codex + User | 2026-08-03 | Payables and receivables report stress both have meaningful execution evidence; receivables is healthy at the current `100-user` tier and payables is healthy on fresh clean reruns, with earlier tail-heavy behavior now treated as runtime-sensitive rather than a confirmed steady-state code bottleneck | Yes | Read/report reruns should now focus on reproducibility across runtime stacks and any remaining high-tier read overlap |
| 2 | Transaction Mutation Stress | In Progress | Codex + User | 2026-08-03 | Sales, purchase, payment, and receipt write stress are functionally clean through multiple reruns; sales is mostly complete for the current mutation-stress tier, purchase now also has a clean mixed 100-user rerun after detail-read stabilization, and vouchers are broadly stable through the 100-user mixed tier with the receipt approval conflict rerun also completing cleanly on the corrected pooled local stack | Yes | Purchase remaining gap is concentrated in isolated 100-user draft-write pressure; sales remaining gaps are mostly settings-tail polish and wider receivables overlap; voucher remaining gap is now more about tail latency and broader mixed overlap than stale-submit correctness |
| 3 | Reporting And Export Stress | In Progress | Codex + User | 2026-08-03 | Heavy financial/report smoke and mixed report-write runs exist with focused optimizations already validated; payables now looks healthy on clean reruns, so the clearest remaining report-hardening focus shifts to financial-report tail latency and export overlap | Yes | Higher-tier financial report stress and export overlap still need broader execution, with payables retained mainly as a reproducibility check |
| 4 | Onboarding, Access, And Bootstrap Stress | Planned | TBD | Not started | Pending | Yes | Includes new user and new entity |
| 5 | Mixed Concurrency And Breakpoint Testing | Planned | TBD | Not started | Pending | Yes | Final resilience and saturation phase |

---

## Phase Execution Notes

## Phase 0 Notes

- Status: `In progress`
- Summary:
  - Phase 0 has moved from planning into setup validation.
  - Local baseline assumptions were captured.
  - Existing Locust tooling and prior performance artifacts were confirmed in repo.
  - Initial hot-route shortlist was defined for first execution.
  - First fresh local smoke baseline was executed with the existing Locust read-only profile.
- Observations:
  - Backend local probe is reachable on `127.0.0.1:8000`.
  - Repo already includes `Finacc/perf/locust` with read, lifecycle, and purchase baseline artifacts.
  - The current stress runbook can reuse existing Locust scaffolding instead of creating new tooling first.
  - Frontend validation still needs actual browser-run confirmation during baseline execution.
  - Read-only smoke run completed with `0` failures across `59` requests.
  - Scoped local dataset behind the slow sales full-list route is `4435` sales invoices for `entity_id=10`, `entityfinid_id=8`, `subentity_id=8`.
  - Most metadata and report endpoints stayed in low hundreds of milliseconds to around `1.1s`.
  - `sales/settings [get]` is moderately expensive but still far below the main outlier.
  - The legacy `sales/invoices [list]` endpoint is the dominant bottleneck by a very large margin.
  - Modern lookup and cross-mode navigation traffic completed a separate smoke baseline with `0` failures across `168` requests and healthy latency.
- Metrics:
  - Run profile:
    - tool: `Locust`
    - date: `2026-08-01`
    - mode: read-only
    - users: `5`
    - spawn rate: `1`
    - duration: `1m`
    - artifacts:
      - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_stats.csv`
      - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_stats_history.csv`
      - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_failures.csv`
      - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_exceptions.csv`
      - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01.html`
  - Aggregate result:
    - requests: `59`
    - failures: `0`
    - average latency: `3354 ms`
    - median latency: `380 ms`
    - p95 latency: approximately `18000 ms`
    - p99 latency: approximately `20000 ms`
  - Key endpoint observations:
    - `auth/login`
      - median: `410 ms`
      - p95: `720 ms`
    - `auth/me`
      - median: `130 ms`
      - p95: `260 ms`
    - `reports/payables/meta [get]`
      - median: `120 ms`
      - p95: `380 ms`
    - `reports/payables/aging [get]`
      - median: `630 ms`
      - p95: `1100 ms`
    - `bank-reconciliation/meta [get]`
      - median: `99 ms`
      - p95: `230 ms`
    - `sales/settings [get]`
      - median: `910 ms`
      - p95: `2000 ms`
    - `sales/invoices/lookup [list]`
      - median: `430 ms`
      - p95: `850 ms`
    - `sales/service-invoices/lookup [list]`
      - median: `300 ms`
      - p95: `910 ms`
    - `sales/invoices [list]`
      - median: `16000 ms`
      - p95: `20000 ms`
      - max: `19529 ms`
      - this is the clear Phase 0 read-path outlier
  - Modern read result:
    - tool: `Locust`
    - date: `2026-08-01`
    - mode: read-modern
    - users: `5`
    - spawn rate: `1`
    - duration: `1m`
    - artifacts:
      - `Finacc/perf/locust/results_phase0_read_modern_5u_1m_2026_08_01_stats.csv`
      - `Finacc/perf/locust/results_phase0_read_modern_5u_1m_2026_08_01_stats_history.csv`
      - `Finacc/perf/locust/results_phase0_read_modern_5u_1m_2026_08_01_failures.csv`
      - `Finacc/perf/locust/results_phase0_read_modern_5u_1m_2026_08_01_exceptions.csv`
      - `Finacc/perf/locust/results_phase0_read_modern_5u_1m_2026_08_01.html`
  - Modern read aggregate:
    - requests: `168`
    - failures: `0`
    - average latency: `176 ms`
    - median latency: `160 ms`
    - p95 latency: approximately `320 ms`
    - p99 latency: approximately `450 ms`
  - Modern read endpoint observations:
    - `sales/invoices/lookup [list]`
      - average: `223 ms`
      - median: `220 ms`
      - p95: `310 ms`
      - p99: `520 ms`
    - `sales/service-invoices/lookup [list]`
      - average: `212 ms`
      - median: `200 ms`
      - p95: `390 ms`
    - `purchase/purchase-invoices/lookup [list]`
      - average: `132 ms`
      - median: `140 ms`
      - p95: `180 ms`
    - `purchase/purchase-service-invoices/lookup [list]`
      - average: `158 ms`
      - median: `140 ms`
      - p95: `210 ms`
      - p99: `430 ms`
    - `sales/invoices/cross-mode-nav [goods->service]`
      - average: `183 ms`
      - median: `180 ms`
      - p95: `310 ms`
    - `sales/service-invoices/cross-mode-nav [service->goods]`
      - average: `137 ms`
      - median: `140 ms`
      - p95: `190 ms`
    - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
      - average: `280 ms`
      - median: `270 ms`
      - p95: `450 ms`
    - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
      - average: `123 ms`
      - median: `120 ms`
      - p95: `170 ms`
- Defects:
  - `P1 candidate`
    - legacy `GET /api/sales/invoices/` list endpoint is extremely slow under even low-concurrency read load
    - relative performance is far worse than lookup endpoints and report meta endpoints
    - likely serializes a large full-list payload for a scoped dataset of `4435` rows
    - requires profiling before the baseline is scaled up
- Decision:
  - Proceed to Phase 0 execution run using existing Locust setup and local browser-backed validation.
  - Do not enable write scenarios until safe target dataset and reset strategy are confirmed.
  - Before raising read baseline concurrency, inspect `sales/invoices [list]` with query profiling and compare whether the intended modern UI path can avoid dependence on the legacy full-list route.
  - Treat the modern lookup/navigation read mix as the practical UI baseline and track the legacy full-list route as a separate hotspot.
  - Next recommended execution:
    - run purchase modern profile
    - run higher-concurrency `read-modern` baseline
    - isolate whether the main baseline should exclude or separately track the legacy sales full-list route
    - confirm the legacy list route after queryset fix under smoke load

### Phase 0 Follow-Up: Legacy Sales Invoice List Profile And Fix

- Direct local profile before queryset fix:
  - route: `GET /api/sales/invoices/`
  - scope: `entity_id=10`, `entityfinid_id=8`, `subentity_id=8`
  - elapsed time: approximately `5775 ms`
  - SQL queries captured: `9000+` before query-log truncation
  - response bytes: `2286341`
- Root cause confirmed:
  - the list queryset used `.only(...)` while deferring header fields that `SalesInvoiceListSerializer` immediately reads
  - deferred fields included:
    - `is_legacy_imported`
    - `legacy_source_system`
    - `legacy_source_key`
    - `legacy_import_mode`
    - `location`
  - this created a large per-row deferred-field query storm
- Backend fix applied:
  - file: [sales_invoice_views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_invoice_views.py)
  - change: expanded `.only(...)` to include the serializer-accessed header fields
- Direct local profile after queryset fix:
  - elapsed time: approximately `497 ms`
  - SQL queries captured: `129`
  - response bytes: `2286341`

### Phase 0 Follow-Up: Post-Fix Read Smoke Rerun

- Run profile:
  - tool: `Locust`
  - date: `2026-08-01`
  - mode: read-only post-fix verification
  - users: `5`
  - spawn rate: `1`
  - duration: `1m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_postfix_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_postfix_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_postfix_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_postfix_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_5u_1m_2026_08_01_postfix.html`
- Aggregate result:
  - requests: `148`
  - failures: `0`
  - average latency: `278 ms`
  - median latency: `200 ms`
  - p95 latency: approximately `670 ms`
  - p99 latency: approximately `880 ms`
- Key endpoint observations:
  - `sales/invoices [list]`
    - average: `632 ms`
    - median: `600 ms`
    - p95: `850 ms`
    - p99: `970 ms`
  - `sales/invoices/lookup [list]`
    - average: `247 ms`
    - median: `220 ms`
    - p95: `400 ms`
    - p99: `660 ms`
  - `sales/settings [get]`
    - average: `496 ms`
    - median: `420 ms`
    - p95: `880 ms`
- Interpretation:
  - the previously dominant list-route outlier improved by an order of magnitude at smoke load
  - the payload is still large, so higher-concurrency working-load reruns are still required
  - Phase 0 can now move forward without the legacy list route completely distorting the read baseline

### Phase 0 Follow-Up: 20-User Working-Load Probe

- Run A:
  - tool: `Locust`
  - date: `2026-08-01`
  - mode: `read-modern`
  - users: `20`
  - spawn rate: `2`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01.html`
- Modern aggregate result:
  - requests: `461`
  - failures: `0`
  - average latency: `3374 ms`
  - median latency: `2300 ms`
  - p95 latency: approximately `8100 ms`
  - p99 latency: approximately `13000 ms`
- Modern endpoint observations:
  - `sales/invoices/lookup [list]`
    - average: `4325 ms`
    - median: `4400 ms`
    - p95: `5400 ms`
  - `sales/service-invoices/lookup [list]`
    - average: `4438 ms`
    - median: `4400 ms`
    - p95: `5100 ms`
  - `sales/invoices/cross-mode-nav [goods->service]`
    - average: `6376 ms`
    - median: `6300 ms`
    - p95: `7500 ms`
  - `purchase/purchase-invoices/lookup [list]`
    - average: `1757 ms`
    - median: `1800 ms`
    - p95: `2400 ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - average: `12349 ms`
    - median: `12000 ms`
    - p95: `14000 ms`

- Run B:
  - tool: `Locust`
  - date: `2026-08-01`
  - mode: `read` excluding `read-modern`
  - users: `20`
  - spawn rate: `2`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_legacy_mix_20u_2m_2026_08_01_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_legacy_mix_20u_2m_2026_08_01_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_legacy_mix_20u_2m_2026_08_01_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_legacy_mix_20u_2m_2026_08_01_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_legacy_mix_20u_2m_2026_08_01.html`
- Legacy-mix aggregate result:
  - requests: `189`
  - failures: `0`
  - average latency: `9208 ms`
  - median latency: `2000 ms`
  - p95 latency: approximately `33000 ms`
  - p99 latency: approximately `36000 ms`
- Legacy-mix endpoint observations:
  - `sales/invoices [list]`
    - average: `30707 ms`
    - median: `31000 ms`
    - p95: `36000 ms`
  - `sales/settings [get]`
    - average: `14603 ms`
    - median: `14000 ms`
    - p95: `16000 ms`
  - `reports/payables/aging [get]`
    - average: `8486 ms`
    - median: `8600 ms`
    - p95: `9900 ms`
  - `bank-reconciliation/meta [get]`
    - average: `1421 ms`
    - median: `1400 ms`
    - p95: `1800 ms`
  - `bank-reconciliation/sessions [list]`
    - average: `1345 ms`
    - median: `1400 ms`
    - p95: `1900 ms`

- Interpretation:
  - both 20-user runs completed with `0` failures, so correctness on the read path remained stable under this probe
  - however, the local environment is already beyond a healthy “working load” threshold at `20` concurrent users
  - the `read-modern` profile is functionally stable, but latency is too high to call `20` users healthy on this environment
  - the legacy/read-mix profile is clearly not acceptable at `20` users because a few routes dominate tail latency:
    - `sales/invoices [list]`
    - `sales/settings [get]`
    - `reports/payables/aging [get]`
    - purchase and sales cross-mode navigation endpoints
  - the next best Phase 0 action is to narrow the practical local ceiling with `10` to `15` user probes, then optimize the remaining hot routes before pushing wider

### Phase 0 Follow-Up: 10-User Modern Narrowing Pass

- Run profile:
  - tool: `Locust`
  - date: `2026-08-01`
  - mode: `read-modern`
  - users: `10`
  - spawn rate: `2`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_modern_10u_2m_2026_08_01_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_10u_2m_2026_08_01_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_10u_2m_2026_08_01_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_10u_2m_2026_08_01_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_10u_2m_2026_08_01.html`
- Aggregate result:
  - requests: `591`
  - failures: `0`
  - average latency: `216 ms`
  - median latency: `180 ms`
  - p95 latency: approximately `520 ms`
  - p99 latency: approximately `980 ms`
- Endpoint observations:
  - `sales/invoices/lookup [list]`
    - average: `287 ms`
    - median: `250 ms`
    - p95: `550 ms`
    - p99: `630 ms`
  - `sales/service-invoices/lookup [list]`
    - average: `267 ms`
    - median: `230 ms`
    - p95: `510 ms`
    - p99: `790 ms`
  - `sales/invoices/cross-mode-nav [goods->service]`
    - average: `268 ms`
    - median: `200 ms`
    - p95: `780 ms`
    - p99: `1300 ms`
  - `purchase/purchase-invoices/lookup [list]`
    - average: `138 ms`
    - median: `130 ms`
    - p95: `230 ms`
    - p99: `500 ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - average: `379 ms`
    - median: `250 ms`
    - p95: `980 ms`
    - p99: `1800 ms`
- Interpretation:
  - this run stayed fully stable with `0` failures and far healthier latency than the `20` user probe
  - for the local environment, `10` concurrent users currently looks like a realistic working baseline for the modern read profile
  - the first clear degradation candidates even at `10` users are still the cross-mode navigation endpoints, especially purchase goods-to-service navigation
  - the next best narrowing step is `15` users on the same modern profile, followed by targeted profiling if the cross-mode routes jump non-linearly

### Phase 0 Follow-Up: 15-User Modern Narrowing Pass

- Run profile:
  - tool: `Locust`
  - date: `2026-08-01`
  - mode: `read-modern`
  - users: `15`
  - spawn rate: `2`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_modern_15u_2m_2026_08_01_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_15u_2m_2026_08_01_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_15u_2m_2026_08_01_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_15u_2m_2026_08_01_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_15u_2m_2026_08_01.html`
- Aggregate result:
  - requests: `851`
  - failures: `0`
  - average latency: `282 ms`
  - median latency: `200 ms`
  - p95 latency: approximately `810 ms`
  - p99 latency: approximately `1200 ms`
- Endpoint observations:
  - `sales/invoices/lookup [list]`
    - average: `361 ms`
    - median: `290 ms`
    - p95: `810 ms`
    - p99: `940 ms`
  - `sales/service-invoices/lookup [list]`
    - average: `369 ms`
    - median: `310 ms`
    - p95: `1000 ms`
    - p99: `1100 ms`
  - `sales/invoices/cross-mode-nav [goods->service]`
    - average: `374 ms`
    - median: `250 ms`
    - p95: `1100 ms`
    - p99: `1400 ms`
  - `purchase/purchase-invoices/lookup [list]`
    - average: `167 ms`
    - median: `130 ms`
    - p95: `370 ms`
    - p99: `500 ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - average: `553 ms`
    - median: `370 ms`
    - p95: `1400 ms`
    - p99: `2400 ms`
- Interpretation:
  - this run also remained fully stable with `0` failures
  - `15` concurrent users is still serviceable on local, but the degradation band is now visible and no longer “comfortably healthy”
  - the sharpest stress growth remains concentrated in purchase and sales cross-mode navigation, with purchase goods-to-service navigation showing the worst tail
  - taken together with the `10` and `20` user runs, the practical local ceiling is now clear:
    - `10` users: healthy baseline
    - `15` users: acceptable but degraded
    - `20` users: saturated for modern read load

## Phase 1 Notes

- Status: `In progress`
- Summary:
  - Read-heavy stress is now partially executed rather than untouched.
  - Receivables has a healthy `100-user` story in the current evidence set.
  - Payables no longer looks like a stable top read-path bottleneck on fresh clean stacks.
- Observations:
  - Earlier payables `100-user / 45-second` evidence on the older `127.0.0.1:8010` stack was tail-heavy.
  - Fresh clean reruns on `127.0.0.1:8011` and `127.0.0.1:8012` were both healthy at the same payables tier.
  - The simple `threads` explanation did not hold, because both clean `threads=8` and clean `threads=2` reruns stayed healthy.
  - Payables should now be tracked as a runtime-comparison and reproducibility problem before being treated as a pure query-optimization problem again.
- Metrics:
  - See:
    - `Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md`
    - `Finacc/docs/performance/payables-runtime-comparison-checklist-2026-08-03.md`
- Defects:
  - No confirmed payables correctness defect in the current reruns.
  - The remaining defect class is unexplained runtime divergence between older and fresh server stacks.
- Decision:
  - Keep Phase 1 open for reproducibility checks and broader read overlap, but do not keep classifying payables as the clearest pure read-path bottleneck unless the slow behavior reproduces on a fresh clean stack.

## Phase 2 Notes

- Status: `Not started`
- Summary:
  - Pending execution
- Observations:
  - None yet
- Metrics:
  - Pending
- Defects:
  - None yet
- Decision:
  - Pending

## Phase 3 Notes

- Status: `In progress`
- Summary:
  - Reporting stress has meaningful execution evidence and several validated optimizations.
  - With payables healthy on fresh clean reruns, the clearest remaining Phase 3 hardening target is now financial-report tail latency.
- Observations:
  - Payables and receivables report paths both have materially better evidence than the early read bottleneck picture suggested.
  - Financial reports remain correctness-safe through current stress tiers, but their peak tail is still the more convincing unresolved reporting bottleneck.
  - Export overlap and higher-tier mixed report stress still need broader execution after the current tail focus.
- Metrics:
  - See:
    - `Finacc/docs/performance/financial-reports-performance-stress-plan-2026-08-02.md`
    - `Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md`
- Defects:
  - Financial-report peak tail remains an active tuning target.
- Decision:
  - Prioritize financial-report tail-cost reduction and only keep payables in this phase as a reproducibility guardrail.

## Phase 4 Notes

- Status: `Not started`
- Summary:
  - Pending execution
- Observations:
  - None yet
- Metrics:
  - Pending
- Defects:
  - None yet
- Decision:
  - Pending

## Phase 5 Notes

- Status: `Not started`
- Summary:
  - Pending execution
- Observations:
  - None yet
- Metrics:
  - Pending
- Defects:
  - None yet
- Decision:
  - Pending

---

## Recommended Execution Order

1. Phase 0
2. Phase 1
3. Fix any read-path blockers
4. Phase 2
5. Fix mutation blockers
6. Phase 3
7. Fix report/export blockers
8. Phase 4
9. Fix onboarding/bootstrap blockers
10. Phase 5
11. Consolidated rerun

---

## Final Outcome We Want

By the end of this program, we should know:

- safe operating load
- peak tolerated load
- known bottlenecks
- highest-risk mutation paths
- highest-risk report/export paths
- whether new entities are production-safe by default
- whether the product is ready for wider production traffic with controlled confidence

---

## Appendix: 2026-08-01 Shared Gating Optimization Follow-Up

- Change area:
  - `Finacc/subscriptions/services.py`
- Why this pass was needed:
  - both `sales/settings [get]` and `reports/payables/aging [get]` were repeatedly reloading the same active subscription and plan-limit rows during a single request
  - this made subscription gating a cross-cutting latency and query-count multiplier
- Applied fix:
  - memoized default `ensure_active_subscription(...)` results on `customer_account`
  - prefetched `plan__limits` with the subscription
  - cached plan-limit maps on the resolved `plan`
  - avoided repeating plan-catalog/default-limit normalization for the same plan instance inside one request
- Direct before/after measurements:
  - `sales/settings [get]`
    - before: `201.58 ms`, `176` queries
    - after: `187.27 ms`, `78` queries
  - `reports/payables/aging [get]`
    - before: `774.88 ms`, `60` queries
    - after: `735.18 ms`, `29` queries
- Result:
  - `sales/settings [get]`
    - query reduction: about `56%`
    - latency reduction: about `7%`
  - `reports/payables/aging [get]`
    - query reduction: about `52%`
    - latency reduction: about `5%`
- Residual hotspots after this fix:
  - `sales/settings [get]`
    - repeated current-doc lookups
    - repeated document-number-series lookups
    - repeated stock-policy and choice-override reads
  - `reports/payables/aging [get]`
    - now appears more constrained by report assembly and payload serialization than by subscription gating
- Recommended next pass:
  - collapse repeated numbering/current-doc helpers inside sales settings
  - profile report assembly functions inside payables aging

### Appendix Follow-Up: Sales Settings Duplicate Preview Collapse

- Date: `2026-08-01`
- Change area:
  - `Finacc/sales/views/sales_settings_views.py`
- Problem observed after the shared gating fix:
  - `sales/settings [get]` was still resolving current-document previews twice
  - the same numbering/current-doc work was executed once for `current_doc_numbers` and again for `numbering_series`
- Applied fix:
  - computed `current_doc_numbers` once in `_payload(...)`
  - reused that result inside `_series_payload(...)` instead of calling `SalesSettingsService.get_current_doc_no(...)` a second time
- Measured result:
  - `sales/settings [get]`
    - before this pass: `187.27 ms`, `78` queries
    - after this pass: `127.48 ms`, `66` queries
- Net effect of this pass:
  - query reduction: about `15%`
  - latency reduction: about `32%`
- Current residual hotspots on `sales/settings [get]`:
  - repeated numbering series reads
  - repeated sales header previous-document lookups
  - repeated stock-policy and choice-override reads

### Appendix Follow-Up: AP Aging Summary Lightweight Selector

- Date: `2026-08-01`
- Change area:
  - `Finacc/reports/selectors/payables.py`
  - `Finacc/reports/services/payables.py`
- Problem observed after the shared gating fix:
  - AP aging summary view was still materializing heavy `VendorBillOpenItem` model rows with related objects even though summary mode only needed scalar fields for vendor/bucket rollups
- Applied fix:
  - added a lightweight summary iterator returning values-based rows for summary mode
  - changed `build_ap_aging_report(...)` summary view to skip the heavy `asof_open_item_balances(...)` model path
- Measured result:
  - `reports/payables/aging [get]` summary
    - before this pass: `735.18 ms`, `29` queries
    - after this pass: `334.62 ms`, `29` queries
- Net effect of this pass:
  - query count stayed flat
  - latency reduction: about `54%`
  - CPU profile reduction: about `1.107 s -> 0.474 s`

### Appendix Follow-Up: AP Aging Invoice Pagination-First Drilldowns

- Date: `2026-08-01`
- Change area:
  - `Finacc/reports/services/payables.py`
  - `Finacc/reports/selectors/payables.py`
- Problem observed:
  - invoice-mode AP aging was constructing drilldown payloads and route resolution for the full unpaginated result set before pagination
  - invoice rows also triggered repeated vendor ledger refreshes because the selector did not include `vendor__ledger__name`
- Applied fix:
  - moved invoice row drilldown/meta/trace decoration to post-pagination so only returned rows are decorated
  - added `vendor__ledger__name` to the open-item selector field list to stop `effective_accounting_name` refresh churn
- Measured result:
  - `reports/payables/aging [get]` invoice view, page `1`, page size `100`
    - baseline before these invoice-specific passes: about `4186.16 ms`, query logging overflowed beyond `9000`
    - after post-pagination drilldown decoration: about `1797.15 ms`, `5745` queries
    - after selector field completion: about `835.30 ms`, `229` queries
- Net effect across the invoice-specific passes:
  - latency reduction: about `80%`
  - query reduction: from `9000+` logged down to `229`
  - CPU profile reduction: about `8.22 s -> 1.27 s`

### Appendix Follow-Up: Phase 0 Modern Read 20-User Rerun

- Date: `2026-08-01`
- Run profile:
  - mode: `read-modern`
  - users: `20`
  - spawn rate: `5`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_postfix2_stats.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_postfix2_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_postfix2_failures.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_postfix2_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_read_modern_20u_2m_2026_08_01_postfix2.html`
- Aggregate comparison versus original `20u` modern-read baseline:
  - baseline:
    - requests: `461`
    - failures: `0`
    - average latency: `3374 ms`
    - median latency: `2300 ms`
    - p95 latency: `8100 ms`
    - p99 latency: `13000 ms`
  - rerun after optimizations:
    - requests: `1139`
    - failures: `0`
    - average latency: `276 ms`
    - median latency: `170 ms`
    - p95 latency: `820 ms`
    - p99 latency: `1500 ms`
- Key route improvements:
  - `sales/invoices/lookup [list]`
    - `4324 ms -> 346 ms`
  - `sales/service-invoices/lookup [list]`
    - `4438 ms -> 369 ms`
  - `sales/invoices/cross-mode-nav [goods->service]`
    - `6376 ms -> 345 ms`
  - `sales/service-invoices/cross-mode-nav [service->goods]`
    - `3233 ms -> 158 ms`
  - `purchase/purchase-invoices/lookup [list]`
    - `1757 ms -> 154 ms`
  - `purchase/purchase-service-invoices/lookup [list]`
    - `1738 ms -> 165 ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - `12349 ms -> 702 ms`
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
    - `3797 ms -> 264 ms`
- Interpretation:
  - the optimized modern-read mix is now stable and materially healthier at `20` concurrent users on the local environment
  - throughput rose sharply while latency collapsed across both sales and purchase modern routes
  - the remaining tail inside modern-read is now concentrated mostly in purchase cross-mode navigation rather than broad list/report endpoints

### Appendix Follow-Up: Legacy Purchase Search Investigation

- Date: `2026-08-01`
- Change area:
  - `Finacc/purchase/views/purchase_invoice.py`
  - `Finacc/purchase/urls.py`
  - `Finacc/perf/locust/locustfile_purchase_legacy.py`
- Problem observed:
  - legacy purchase search stress runs initially appeared to be "auth-only" because users logged in successfully but the legacy search traffic was not clearly surfacing in the aggregate run output
  - direct authenticated probing showed the legacy purchase search endpoint had regressed badly enough to time out at `90s` with `0 bytes` returned before the search-path parity fix
  - service-side legacy search routing was inconsistent with goods-side search routing
- Applied fix:
  - added a dedicated `PurchaseServiceInvoiceSearchAPIView` using the same lightweight search contract as goods search
  - moved `purchase-service-invoices/search/` off the heavier list/create path and onto the dedicated search path
  - added explicit service-line filtering in the search queryset via `Exists(...)` on `PurchaseInvoiceLine`
- Direct endpoint timings after the search-path fix:
  - `GET /api/purchase/purchase-invoices/search/`
    - returned successfully in about `12.69s`
    - payload size about `12.79 MB`
  - `GET /api/purchase/purchase-service-invoices/search/`
    - returned successfully in about `11.76s`
    - payload size about `9.54 MB`
- Harness validation:
  - a minimal authenticated Locust probe against `purchase/purchase-invoices/search [legacy]` with a forced `5s` read timeout did execute the legacy request
  - result:
    - the task reached the endpoint
    - the request failed with `ReadTimeout` at `5s`
- Interpretation:
  - the remaining issue is no longer a Locust dispatch mystery
  - the legacy purchase search routes are reachable and improved, but they are still too slow and too large for meaningful concurrent stress testing in their current unpaginated form
  - next optimization pass should target the legacy search APIs directly:
    - reduce response payload size
    - add pagination or a hard result cap
    - trim serializer/queryset cost for fields not required by the legacy UI contract

### Appendix Follow-Up 2: Legacy Purchase Search Pagination Contract

- Date: `2026-08-01`
- Change area:
  - `Finacc/purchase/views/purchase_invoice.py`
  - `Finacc/purchase/tests.py`
- Applied fix:
  - added default pagination to legacy purchase search endpoints:
    - default page size: `100`
    - client override via `page_size`
    - hard cap: `250`
  - kept both goods and service legacy search routes on the lightweight search views
- Direct endpoint timings after pagination:
  - `GET /api/purchase/purchase-invoices/search/`
    - response time about `0.22s`
    - response shape: `count / next / previous / results`
    - first page returned `100` rows out of `10638`
  - `GET /api/purchase/purchase-service-invoices/search/`
    - response time about `0.28s`
    - response shape: `count / next / previous / results`
    - first page returned `100` rows out of `7917`
- Regression coverage added:
  - `PurchaseApiSmokeTests.test_purchase_invoice_search_returns_paginated_response`
  - `PurchaseApiSmokeTests.test_purchase_service_invoice_search_filters_to_service_headers`
- Targeted test run:
  - command:
    - `python manage.py test purchase.tests.PurchaseApiSmokeTests.test_purchase_invoice_search_returns_paginated_response purchase.tests.PurchaseApiSmokeTests.test_purchase_service_invoice_search_filters_to_service_headers --keepdb`
  - result:
    - `Ran 2 tests in 0.276s`
    - `OK`
- Interpretation:
  - the legacy search endpoints are now fast enough to re-enter the stress matrix
  - the immediate next step is to rerun the legacy purchase Locust profile and capture post-pagination concurrency numbers

### Appendix Follow-Up 3: Legacy Purchase Stress Rerun After Pagination

- Date: `2026-08-01`
- Run profile:
  - harness: `perf/locust/locustfile_purchase_legacy.py`
  - users: `20`
  - spawn rate: `5`
  - duration: `2m`
  - artifacts:
    - `Finacc/perf/locust/results_phase0_purchase_legacy_20u_2m_2026_08_01_postfix7_stats.csv`
    - `Finacc/perf/locust/results_phase0_purchase_legacy_20u_2m_2026_08_01_postfix7_stats_history.csv`
    - `Finacc/perf/locust/results_phase0_purchase_legacy_20u_2m_2026_08_01_postfix7_failures.csv`
    - `Finacc/perf/locust/results_phase0_purchase_legacy_20u_2m_2026_08_01_postfix7_exceptions.csv`
    - `Finacc/perf/locust/results_phase0_purchase_legacy_20u_2m_2026_08_01_postfix7.html`
- Final result:
  - aggregated requests: `710`
  - failures: `0`
  - average latency: `1390 ms`
  - median latency: `1500 ms`
  - p95 latency: `2200 ms`
  - p99 latency: `2400 ms`
  - throughput: `6.05 req/s`
- Route detail:
  - `purchase/purchase-invoices/search [legacy]`
    - requests: `368`
    - failures: `0`
    - average latency: `1455 ms`
    - median latency: `1500 ms`
    - p95 latency: `2200 ms`
    - p99 latency: `2400 ms`
    - throughput: `3.14 req/s`
  - `purchase/purchase-service-invoices/search [legacy]`
    - requests: `302`
    - failures: `0`
    - average latency: `1474 ms`
    - median latency: `1600 ms`
    - p95 latency: `2200 ms`
    - p99 latency: `2400 ms`
    - throughput: `2.57 req/s`
- Comparison versus pre-pagination legacy baseline (`results_purchase_legacy_5u_1m_stats.csv`):
  - goods legacy search:
    - `30266 ms -> 1455 ms`
  - service legacy search:
    - `25160 ms -> 1474 ms`
  - aggregated throughput:
    - `0.31 req/s -> 6.05 req/s`
- Interpretation:
  - the legacy purchase search workload is no longer timing out under concurrent stress
  - pagination converted the legacy search path from effectively unusable under load into a stable, zero-failure read workload
  - the remaining legacy latency is still materially slower than the optimized modern-read mix, but it is now within a usable range for continued stress and regression monitoring
