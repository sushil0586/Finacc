# Compliance Post-Go-Live Support SOP

Date: 2026-05-13  
Owner: Support Team + Engineering + Finance Ops

## Objective

Standardize post-go-live support for compliance modules with:
- predictable response SLAs
- clear ticket workflow
- controlled escalation path
- clean handoff to product backlog

## Scope

Applies to:
- GST Exception Dashboard
- GSTR-1 vs GSTR-3B Reconciliation
- Controls Hub compliance actions
- Purchase Statutory readiness (TDS)
- TCS Workspace and Filing Pack exports
- Withholding Readiness Dashboard

## Support Channels

- Primary: support ticket queue (mandatory logging)
- Secondary: release/incident channel (for active outages)
- Business escalation: implementation/finance lead group

## SLA Targets

- Sev1:
  - Acknowledge: 15 minutes
  - Mitigation plan: 30 minutes
  - Status updates: every 30 minutes
- Sev2:
  - Acknowledge: 1 hour
  - Mitigation plan: 4 hours
  - Status updates: every 4 hours
- Sev3:
  - Acknowledge: 4 business hours
  - Plan: next business day

## Ticket Intake Template

Required fields:
- Module
- Entity
- Financial year
- User role
- URL/screen
- Exact filter scope
- Expected vs actual behavior
- Screenshot/export sample
- Timestamp

## Triage Categories

1. Permission/RBAC issue
2. Data/reconciliation mismatch
3. Export failure/content mismatch
4. Drilldown/navigation failure
5. UI rendering/usability issue
6. Performance/timeout issue

## First-Level Actions

1. Reproduce with same role and scope.
2. Validate permission presence for affected route/API.
3. Re-check scope params (`entity`, `entityfinid`, `subentity`, period).
4. Verify if issue is posted vs non-posted data behavior.
5. Verify export from same filter state.

## Escalation Rules

Escalate to Engineering immediately if:
- user cannot access a critical compliance page
- export is failing for all users
- drilldowns fail for posted data
- mismatch appears due to logic regression (not data state)

Escalate to Finance Ops if:
- source books/data entry inconsistency is root cause
- posting status/data readiness conflict is expected but unclear to user

## Workaround Policy

Allowed short-term workarounds:
- role permission correction
- controlled alternate report path
- guidance note for non-posted source behavior

Not allowed:
- bypassing permission checks
- manual data manipulation without audit trail
- hidden config changes without ticket notes

## Closure Checklist

Ticket closes only after:
1. Reproduction no longer fails.
2. User confirms resolution.
3. Root cause recorded.
4. Preventive action recorded:
- test case added, or
- monitoring rule added, or
- documentation updated.

## Weekly Review

Every week, review:
- top 5 repeated ticket themes
- SLA misses
- unresolved Sev2/Sev3 aging > 7 days
- candidates for automation/tests

## Handoff to Product Backlog

If issue is non-blocking but recurring:
1. Convert ticket into backlog item.
2. Attach evidence and impact count.
3. Tag priority:
- P1 if compliance filing risk
- P2 if frequent user friction
- P3 if cosmetic/documentation

