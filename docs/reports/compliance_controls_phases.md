# Compliance And Controls Phases

Date: 2026-05-13

## Purpose

This document breaks the next compliance and controls workspace into phased execution.

The goal is to keep backend, frontend, UAT, and handover work aligned across:
- GST filing readiness
- TDS and TCS compliance reporting
- controls dashboard
- audit trail and voucher drilldowns

## Working Principles

Use these rules while implementing the phases:

1. Prefer extending existing report and controls services before creating parallel report stacks.
2. Reuse the financial hub export and filter hardening pattern for new compliance surfaces.
3. Prefer one drilldown language across reports, posting detail, and source documents.
4. Surface user-facing readiness states early, even before all drilldowns and secondary reports are complete.
5. Keep every phase shippable for UAT on its own.

## Phase 1: GSTR-1 Readiness Foundation

Focus:
- consolidate GSTR-1 validations into one readiness workspace
- add action-oriented warnings
- surface `ready to file`, `blocked`, and `review` state
- make export and validation feel like one flow

Backend scope:
- extend GSTR-1 validation payloads with grouped warning categories, counts, and recommended actions
- add a top-level readiness summary on the GSTR-1 reporting surface
- define severity-to-status rules for `ready_to_file`, `review`, and `blocked`
- attach export actions in the same payload used for readiness review
- keep existing section, table, and invoice endpoints reusable

Frontend scope:
- align the GSTR-1 screen around one primary readiness workspace
- show summary, blockers, review items, and export actions in one flow
- modernize inconsistent GST widgets if they still differ from the current financial hub standard

Deliverables:
- consolidated GSTR-1 readiness API contract
- action-oriented validation messages
- readiness status banner and summary cards
- export actions embedded into the readiness workspace
- updated GST UAT checklist for readiness behavior

Acceptance:
- a user can understand filing readiness without jumping across multiple screens
- exported scope always matches the validated scope
- blockers are distinguishable from review items

## Phase 2: Voucher Drilldowns And Audit Trust

Focus:
- add trust-building drillthrough from close, opening, and compliance outputs
- let users click through to posted vouchers and source documents

Backend scope:
- reuse existing posting detail and document lookup flows where possible
- add drilldown metadata to year-close, opening, and compliance responses
- standardize drilldown payload shape across report families
- expose voucher numbers, posting entry ids, and source document references where available

Frontend scope:
- add clickable drilldowns from summary cards, warnings, and report rows
- present voucher and source-document navigation consistently

Deliverables:
- drilldown contract shared by controls and compliance reports
- year-close and opening preview drilldowns
- compliance warning drilldowns to source transactions and postings
- UAT notes covering traceability checks

Acceptance:
- finance users can trace a warning or control result to the posted accounting entry
- UAT reviewers can verify source-to-report trust without manual SQL or admin inspection

## Phase 3: Controls Dashboard

Focus:
- one controls page for posting setup, year close, opening generation, validation warnings, and compliance readiness

Backend scope:
- aggregate existing controls services into a single dashboard payload
- reuse current opening policy, opening preview, posting setup, and year-end close services
- add compliance readiness summary blocks fed by GST readiness outputs
- expose status cards, next steps, and action links

Frontend scope:
- create a single controls shell with sections for:
  - posting setup
  - year close
  - opening generation
  - validation warnings
  - compliance readiness
- align layout and interactions with the stronger financial hub experience

Deliverables:
- controls dashboard API
- unified controls page in Angular
- dashboard cards with status, action, and drilldown links

Acceptance:
- one page answers “what is configured”, “what is blocked”, and “what should finance do next”
- controls status is consistent with underlying detail pages

## Phase 4: TDS And TCS Compliance Reporting

Focus:
- verify current coverage
- modernize UI if still inconsistent
- harden exports and filters like the financial hub

Backend scope:
- audit current GST-TDS and withholding/TCS coverage
- identify what is config-only, workflow-only, and report-ready
- add or extend report surfaces for monthly compliance status, exceptions, and filing readiness
- standardize filter handling, pagination, and export actions
- add CSV and Excel export support where missing

Frontend scope:
- bring TDS and TCS reporting screens closer to GST and financial hub patterns
- use the same export/filter/readiness conventions where appropriate

Deliverables:
- coverage audit summary
- TDS/TCS reporting gap list
- hardened report APIs with filters and exports
- UI alignment for report-ready TDS/TCS workspaces

Acceptance:
- report consumers can filter, review, and export TDS/TCS data with the same confidence they have in newer report modules
- coverage gaps are explicit rather than hidden in admin or workflow screens

## Phase 5: UAT Hardening And Handover

Focus:
- stabilize the full workspace for finance review and rollout

Scope:
- regression test compliance and controls endpoints
- verify exports against screen totals and scope
- validate drilldowns against posted voucher history
- refresh admin, user, and UAT documentation
- close naming inconsistencies and final UI rough edges

Deliverables:
- updated UAT checklist items
- rollout notes by phase
- known-issues list if any deferred items remain

Acceptance:
- finance and implementation teams can run structured UAT without engineering assistance
- production rollout risks are documented and bounded

## Recommended Build Order

Implement in this order:

1. Phase 1: GSTR-1 Readiness Foundation
2. Phase 2: Voucher Drilldowns And Audit Trust
3. Phase 3: Controls Dashboard
4. Phase 4: TDS And TCS Compliance Reporting
5. Phase 5: UAT Hardening And Handover

Reasoning:
- GSTR-1 readiness gives the fastest visible value for filing workflows.
- Drilldowns make later controls and compliance states more trustworthy.
- The controls dashboard becomes much stronger after readiness and drilldown primitives exist.
- TDS/TCS work benefits from the shared export, filter, and UI conventions established earlier.

## Notes For Execution

- Backend work will begin in `finacc-django`.
- Frontend modernization should target the Angular workspace in `../accountproject`.
- If a phase reveals missing menu, permission, or route access, include that work in the same phase rather than deferring it silently.
