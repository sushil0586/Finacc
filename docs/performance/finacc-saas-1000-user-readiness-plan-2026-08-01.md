# Finacc SaaS 1000-User Readiness Plan

Last updated: 2026-08-01

Status: planned

Related documents:
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [finacc-stress-phase1-write-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-write-plan-2026-08-01.md:1)
- [finacc-stress-phase1-execution-matrix-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-execution-matrix-2026-08-01.md:1)
- [finacc-saas-phaseA-100-user-baseline-execution-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-saas-phaseA-100-user-baseline-execution-2026-08-01.md:1)

## Purpose

This document answers one specific production question:

Can Finacc operate safely as a SaaS product for up to `1000` users?

That question must be split into practical sub-questions:

- can the platform support `1000 registered users`?
- can it support `1000 provisioned users across many entities`?
- can it support `1000 concurrently active sessions`?
- can it support `1000 users with realistic staggered business-day behavior`?
- what is the safe concurrent write limit?
- what is the safe mixed read/write/reporting limit?

The goal is not to claim a number early.

The goal is to prove the number with evidence.

## Current Honest Position

As of 2026-08-01:

- low-load correctness confidence is strong in several operational areas
- purchase read and purchase write stress at small scale is stable
- we have not yet proven `100`, `250`, `500`, or `1000` active-user readiness
- we do not yet have enough evidence for a production claim of `1000 concurrent active users`

So today:

- `1000 registered users`: likely feasible
- `1000 provisioned SaaS users across tenants`: likely feasible
- `1000 simultaneous active users`: not yet proven
- `1000 simultaneous write-heavy users`: not yet credible without phased evidence

## Definitions

To avoid confusion, use these terms consistently.

### Registered users

Users who exist in the system but may not be active at the same time.

### Active sessions

Logged-in users with live tabs open.

### Concurrent active users

Users making requests during the same time window.

### Working-load concurrency

Normal business-day overlap where a subset of users are active together.

### Peak concurrency

Temporary burst overlap such as month-end, posting day, or reporting rush.

### Write-heavy concurrency

High overlap of invoice save/post, voucher posting, approvals, and linked mutations.

## Recommended SaaS Assumption Model

Do not design for `1000 simultaneous heavy operators` unless the business truly needs it.

A more realistic SaaS shape is:

- `1000 total users`
- `150 to 300` active in a busy hour
- `50 to 120` simultaneously performing meaningful operations
- `10 to 40` performing write-heavy mutations at the same time
- a larger set doing reads, filters, lookup, and reports

This assumption should still be validated rather than trusted blindly.

## Readiness Gates

Before claiming `1000-user readiness`, all of the following must be true:

1. Functional correctness remains stable under load.
2. p95 and p99 latency stay within defined SLOs at target working load.
3. Error rate stays controlled at target working load.
4. DB connections, locks, and slow queries remain controlled.
5. Background workers do not accumulate unrecoverable backlog.
6. The system degrades predictably beyond working load.
7. Recovery after pressure removal is clean.
8. No duplicate numbering, corrupt transitions, or silent data loss occurs.

## Required Metrics

For every phase below, capture:

- total requests
- requests per endpoint
- p50, p95, p99 latency
- error rate
- timeout rate
- CPU per app node
- memory per app node
- DB CPU
- DB memory
- DB connection count
- DB wait events / lock waits
- slow query list
- cache / Redis memory and ops
- queue depth for async jobs
- storage and export latencies if exports are involved

Also record:

- exact build hash
- environment topology
- user count
- spawn rate
- duration
- tenant/data size

## Success SLO Draft

These are the initial SaaS-readiness targets.

- login p95: `< 2s`
- customer/vendor/product lookup p95: `< 1s`
- invoice draft save p95: `< 3s`
- invoice post p95: `< 5s`
- payment/receipt save/post p95: `< 4s`
- report refresh p95: `< 8s`
- export trigger p95: `< 5s`
- system-wide error rate at working load: `< 1%`

For stress and breakpoint runs, temporary degradation is acceptable if:

- it is measurable
- it is diagnosable
- it recovers cleanly

## Execution Phases

## Phase A: 100-User Baseline

Goal:
- prove that the product is healthy beyond current low-load validation

Profile mix:
- `60%` read-heavy
- `25%` operational mixed
- `15%` write-heavy

Targets:
- `50`, then `100` concurrent users
- `20` minutes each

Required modules:
- authentication
- sales
- purchase
- vouchers
- payables / receivables reports
- dropdown-heavy master flows

Pass condition:
- zero correctness defects
- controlled p95
- no infra saturation

## Phase B: 250-User Working SaaS Load

Goal:
- simulate realistic busy-hour multi-tenant SaaS usage

Profile mix:
- `55%` read-heavy
- `25%` mixed operational
- `15%` write-heavy
- `5%` reporting/export

Targets:
- `150`
- `200`
- `250`

Duration:
- `20 to 30` minutes

Primary focus:
- DB connections
- hot-query amplification
- lookup/filter endpoints
- session and auth stability

Pass condition:
- acceptable SLO compliance
- no dangerous queue or DB buildup

## Phase C: 500-User Peak Validation

Goal:
- validate peak-hour resilience and identify non-linear slowdowns

Profile mix:
- `50%` read-heavy
- `20%` mixed operational
- `20%` write-heavy
- `10%` reports/exports

Targets:
- `300`
- `400`
- `500`

Duration:
- `30` minutes

Primary focus:
- p99 growth
- lock contention
- queue build-up
- export interference
- infrastructure scaling gaps

Pass condition:
- system remains operational
- failure behavior is controlled and diagnosable

## Phase D: 1000-User Burst Validation

Goal:
- test whether `1000 concurrent active users` is truly supportable

Important:
- this is not the first proof step
- this should only run after earlier phases are stable

Profile mix:
- `60%` read-heavy
- `20%` mixed operational
- `10%` write-heavy
- `10%` reports/exports

Targets:
- `750`
- `1000`

Duration:
- `10 to 20` minutes initial burst
- extend only if stable

Primary focus:
- app node saturation
- DB max connections
- query latency explosion
- cross-tenant interference
- worker backlog
- recovery after burst stops

Pass condition:
- no systemic collapse
- no corruption
- predictable degradation

## Phase E: Breakpoint And Recovery

Goal:
- identify where the architecture truly starts failing

Method:
- ramp above known stable load
- measure exact inflection point
- stop when the environment becomes unsafe
- observe recovery after load removal

Primary focus:
- what breaks first
- whether recovery is automatic
- whether manual intervention is required

## Workload Families For SaaS Proof

Every major phase should include these workload groups.

### Group 1: Login and session

- login
- me/session hydration
- entity switch
- token/session longevity

### Group 2: Lookup-heavy operator activity

- customer search
- vendor search
- product search
- account search
- report filter load

### Group 3: Core write activity

- sales invoice save/confirm/post
- purchase invoice save/confirm/post
- payment/receipt posting
- note creation and linked references

### Group 4: Reporting pressure

- payables
- receivables
- ledger
- cashbook/daybook
- export endpoints

### Group 5: SaaS admin and onboarding

- new registration
- new entity creation
- entity bootstrap
- subscription hydration
- role/feature hydration

## Key Risks To Watch

The likely failure modes for a SaaS ERP are:

- DB connection exhaustion
- slow lookup/search queries
- legacy list endpoints pulling too much data
- high-lock contention during posting
- duplicate numbering under concurrent writes
- heavy reports interfering with transactional routes
- cache misses amplifying DB load
- onboarding/bootstrap spikes creating write bursts

## Current Strong Areas

Based on current evidence:

- low-load purchase write flows are healthy
- modern purchase reads are healthier than legacy purchase reads
- purchase mixed read/write remained correct under moderate local pressure

## Current Weak Or Unproven Areas

- high-scale auth/session behavior
- 100+ user concurrency
- voucher-heavy mixed pressure
- reports and exports at scale
- sales and purchase create/save pressure at larger scale
- onboarding and entity bootstrap under concurrent tenant creation
- full infra saturation behavior

## Recommended Next Execution Order

1. Finish Phase 1 write coverage gaps:
- purchase create/save
- purchase notes
- payment/receipt lifecycle
- mixed report-under-write profile

2. Run `50` and `100` user mixed SaaS baseline.

3. Tune hot routes before attempting `250+`.

4. Run `250` user working-load SaaS profile.

5. Only after clean `250`, attempt `500`.

6. Attempt `1000` only after infra and query evidence justify it.

## What “1000 Users Ready” Should Mean

We should only make that claim when we can say:

- `1000` user scenario definition is explicit
- target topology is documented
- the tested workload mix is documented
- the environment sustained the defined load
- correctness remained intact
- recovery behavior was verified

Without those proofs, the claim should be:

- “not yet validated”

## Status Template

After each phase, append:

### Run

- date:
- environment:
- topology:
- users:
- spawn rate:
- duration:
- workload mix:

### Outcome

- status: `pass` / `partial` / `fail`
- p95:
- p99:
- error rate:
- DB max connections:
- CPU peak:
- memory peak:
- queue backlog:

### Findings

- 

### Action Items

- 
