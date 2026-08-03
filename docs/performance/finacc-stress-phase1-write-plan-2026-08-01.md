# Finacc Stress Phase 1 Write Plan

Last updated: 2026-08-03

Status: actively executed across sales, purchase, and vouchers; higher-tier reruns and reports-under-write remain in progress.

Related documents:
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [invoice-performance-phase0-results.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-phase0-results.md:1)
- [perf/locust/README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md:1)

## Purpose

This document is the execution runbook for Phase 1 of product stress testing.

Phase 1 moves beyond read-heavy baseline measurement and focuses on write-heavy operational pressure:

- live document creation
- draft save
- confirm and post transitions
- linked-document mutation
- approval workflow actions
- report consistency while writes are active

The goal is not only throughput.

The goal is to prove:

- no duplicate numbering
- no corrupted state transitions
- no stale-tab overwrite damage
- no broken links across invoices, notes, vouchers, settlements, or reports
- predictable user-visible behavior under concurrent writes

## Phase 1 Goal

Run a module-wise write-stress pass for:

1. Sales
2. Purchase
3. Vouchers
4. Reports under active writes

This phase should use actual live mutation paths against safe editable data.

## Phase 1 Entry Criteria

Before running any scenario, confirm all of the following:

- backend build frozen for the run
- frontend build frozen for the run
- target entity and subentity confirmed
- numbering sequences known before run
- safe editable test data confirmed
- write-testing environment explicitly approved
- background workers healthy
- DB snapshot or rollback plan available
- logging and API metrics enabled
- browser console/network capture available

## Phase 1 Module Order

### Phase 1A: Sales Write Stress

Focus:
- invoice draft create
- invoice update
- confirm
- post
- unpost where safe
- service and goods mode parity
- linked note creation pressure

### Phase 1B: Purchase Write Stress

Focus:
- purchase invoice draft create
- vendor/header mutation while editing
- confirm
- post
- debit note and credit note flows
- GST/TDS-sensitive mutation paths

### Phase 1C: Voucher Write Stress

Focus:
- payment voucher create/save/post
- receipt voucher create/save/post
- approval-state transitions
- settlement/allocation mutation integrity
- stale approval-state conflicts across tabs

### Phase 1D: Reports During Active Writes

Focus:
- financial reports while mutations are active
- receivables/payables while invoices or vouchers are posting
- export endpoints during write load
- dropdown/filter/meta correctness under concurrent mutations

### Phase 1E: Consolidated Rerun

Focus:
- rerun only the failed or weak scenarios after fixes
- confirm closure with the same evidence format

## Load Ladder

Each module should be executed in increasing pressure.

### Level 0: Write Smoke

- `2 to 5` concurrent users
- `5 to 10` minutes
- target: correctness first

### Level 1: Working Write Load

- `10 to 20` concurrent users
- `15 to 20` minutes
- target: ordinary business-day mutation volume

### Level 2: Peak Write Load

- `25 to 50` concurrent users
- `20 to 30` minutes
- target: busy-hour resilience

### Level 3: Mixed Pressure

- `20 to 50` mixed users
- active writers plus report/export readers
- target: production-like interference

Do not move to higher levels if lower-level correctness is not stable.

## Common Evidence To Capture

For every run, record:

- exact date and time
- environment
- entity and subentity used
- user count
- spawn rate
- duration
- routes exercised
- p50, p95, p99 latency
- total failures
- timeout count
- duplicate numbering count
- validation conflict count
- stale-state conflict count
- console/UI failures
- data integrity observations

Also capture:

- Locust CSV and HTML artifacts
- screenshots for browser-visible failures
- backend tracebacks
- slow query evidence if available

## Module Matrices

## Phase 1A Sales Matrix

### Sales core scenarios

1. Draft create with customer selection and line entry
- create invoice
- save draft
- reopen draft
- confirm no missing line/header data

2. Save, confirm, and post under concurrency
- multiple users create sales invoices
- multiple users confirm and post
- verify unique numbering and correct status

3. Customer change before save under pressure
- switch customer on draft
- validate GST, state, POS, shipping, tax regime
- ensure no stale customer header values persist

4. Service and goods mode parity
- run same mutation flow in goods and service modes
- verify cross-mode navigation and numbering integrity

5. Sales note creation from invoice under pressure
- create credit note / debit note from posted invoice
- verify linked reference and tax derivation

6. Save/post stale-tab conflict
- same document in two tabs
- save in one tab
- post or save in another tab
- verify conflict behavior is safe and user-visible

### Sales pass criteria

- no duplicate bill or voucher numbers
- no wrong customer-derived tax regime
- no missing linked-note reference integrity
- no silent overwrite between tabs

## Phase 1B Purchase Matrix

### Purchase core scenarios

1. Draft create with vendor selection and line entry
- create invoice
- save draft
- reopen
- verify vendor-driven fields are intact

2. Save, confirm, and post under concurrency
- multiple users create purchase invoices
- confirm and post under overlap
- verify numbering and status correctness

3. Vendor switch during draft edit
- change vendor on editable draft
- validate GST, state, POS, tax regime, linked reference behavior
- verify no stale vendor values persist after switch-back

4. Purchase service and goods mode parity
- run the same mutation flow in both modes
- verify navigation and line-mode integrity

5. Purchase note creation under pressure
- create purchase credit note
- create purchase debit note
- verify linked document and tax derivation

6. TDS and TCS sensitive mutation coverage
- run invoice/note flows with active withholding configuration
- verify save, confirm, post, and reportable values

7. Save/post stale-tab conflict
- same document in two tabs
- save in one tab and mutate in another
- ensure safe conflict handling

### Purchase pass criteria

- no duplicate numbering
- no wrong vendor-derived tax regime
- no broken linked-note reference behavior
- no stale write overwrites
- no TDS/TCS corruption under concurrency

## Phase 1C Voucher Matrix

### Payment voucher scenarios

1. Draft create and save
- choose vendor
- save
- reopen
- verify header, lines, and allocations

2. Save and post under overlap
- multiple users create payment vouchers
- verify posting integrity and unique numbering

3. Approval workflow stress
- submit
- approve
- reject
- re-open if supported
- validate state transitions

4. Same voucher in multiple tabs
- save in tab A
- submit or approve in tab B
- verify stale-state protection

5. Allocation and settlement integrity
- mutate linked open items
- confirm no duplicate settlement application

### Receipt voucher scenarios

1. Draft create and save
- choose customer
- save
- reopen
- verify integrity

2. Save and post under overlap
- multiple users create receipts
- verify numbering and status correctness

3. Approval workflow stress
- submit, approve, reject across tabs
- validate stale-state handling

4. Allocation and settlement integrity
- concurrent open-item usage
- ensure no duplicate settlement consumption

### Voucher pass criteria

- no duplicate voucher numbering
- no broken approval transitions
- no double allocation or settlement
- explicit stale-state handling in multi-tab scenarios

## Phase 1D Reports Under Active Writes Matrix

### Core reporting scenarios

1. Ledger and summary reports while invoice writes are active
- ledger book
- ledger summary
- customer and vendor statements

2. Financial statements while posting is active
- trial balance
- balance sheet
- profit and loss
- trading account

3. Operational reports while vouchers are posting
- cashbook
- daybook
- receivables
- payables

4. Export under write pressure
- pdf
- excel
- csv
- confirm export correctness and completion behavior

5. Filter and dropdown meta during active writes
- customer/vendor filters
- account filters
- branch/year filters
- confirm no empty, leaked, or stale options

### Reporting pass criteria

- no report crash under active writes
- no obviously inconsistent totals beyond expected transactional timing windows
- exports finish or fail explicitly
- no broken dropdown/filter hydration

## Failure Classification

Each failure should be tagged as one of:

- `P0 data corruption`
- `P0 duplicate numbering`
- `P0 broken posting state`
- `P1 stale-tab unsafe overwrite`
- `P1 linked-reference integrity defect`
- `P1 report correctness defect under write load`
- `P2 latency degradation`
- `P2 noisy validation conflict`
- `P3 UX weakness or unclear feedback`

## Execution Log Template

Use this section format after each run.

### Run ID

- module:
- date:
- environment:
- entity:
- subentity:
- users:
- spawn rate:
- duration:
- tags or scenario group:

### Result

- status: `pass` / `partial` / `fail`
- p95:
- error rate:
- duplicate numbering:
- stale conflict count:
- broken workflow count:

### Observations

- 

### Defects Found

- 

### Rerun Needed

- yes / no

## Phase 1 Status Tracker

| Subphase | Scope | Status | Last Run Date | Notes |
| --- | --- | --- | --- | --- |
| Phase 1A | Sales write stress | Passed through higher-tier reruns | 2026-08-02 | Mixed and isolated sales write/load reruns are correctness-clean through 100-user comparison tiers; remaining gap is optional low-frequency settings patch trim |
| Phase 1B | Purchase write stress | Passed with refreshed 20-user write evidence; higher-tier reruns remain | 2026-08-03 | Fresh-doc and dropdown-tightening reruns still hold, and a fresh `20-user / 2-minute` mixed plus isolated write rerun stayed correctness-clean with `0` failures; the current latency hotspot is purchase goods/service draft save, so the next gap is higher-tier comparison plus draft-save reduction |
| Phase 1C | Voucher write stress | Passed with targeted follow-up | 2026-08-02 | Payment is strong; receipt create-side tail materially improved after no-op TCS and write-response navigation fixes, but receipt create still needs another reduction pass for SaaS-grade confidence |
| Phase 1D | Reports under active writes | In progress | 2026-08-02 | Heavy report smoke and mixed report-write passes exist; broader higher-tier reporting stress still remains |
| Phase 1E | Consolidated rerun | Planned | - | Depends on defects from 1A to 1D |

## Recommended First Execution Slice

Start with:

1. Sales write smoke
2. Purchase write smoke
3. Payment and receipt write smoke
4. Vendor/customer statement refresh during active posting

Reason:

- these are the highest-value live mutation paths
- they expose duplicate numbering, stale-write, settlement, and linked-reference defects early
- they create the best signal before higher concurrency is introduced

## Exit Criteria For Phase 1

Phase 1 can be marked complete when:

- all four module groups have been executed at least through Level 1
- all P0 and P1 defects have either been fixed or explicitly accepted with mitigation
- reruns confirm no duplicate numbering or data corruption
- write-heavy and mixed write-read runs are documented with artifacts
