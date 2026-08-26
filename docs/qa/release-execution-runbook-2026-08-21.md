# Finacc Release Execution Runbook

Date: 2026-08-21

## Purpose

This runbook turns the release documentation into an execution sequence for release day.

Use it with:

- [Release-Day Checklist](./release-day-checklist-2026-08-21.md)
- [Production Go / No-Go Tracker](./production-go-no-go-tracker-2026-08-21.md)
- [Production Release Granular Verification Matrix](./production-release-granular-verification-matrix-2026-08-21.md)

## Operating Rules

1. Do not start downstream module signoff until platform and scope decisions are complete.
2. Stop immediately on any `Critical` failure that affects auth, posting, reconciliation, reporting totals, or rollback readiness.
3. Record evidence as you go. Do not rely on memory at the end of the day.
4. If a module is out of scope, mark it `Deferred` explicitly in the tracker.

## Team Slots

Assign names before execution starts.

| Role | Owner |
| --- | --- |
| Release lead | `TBD` |
| Backend lead | `TBD` |
| Frontend lead | `TBD` |
| QA lead | `TBD` |
| Finance / business signoff | `TBD` |
| Payroll signoff | `TBD` |
| Infra / DevOps | `TBD` |
| Support / incident owner | `TBD` |

## Evidence Locations

| Type | Location |
| --- | --- |
| Playwright report | `/Users/ansh/Documents/finacc-ui-tests/playwright-report` |
| Test artifacts | `/Users/ansh/Documents/finacc-ui-tests/test-results*` |
| Manual signoff notes | `TBD` |
| Export/output captures | `TBD` |
| Rollback/support notes | `TBD` |

## Phase 0: Pre-Start

Goal:
- freeze scope
- assign owners
- confirm environments and evidence locations

Checklist:

| Step | Owner | Status | Notes |
| --- | --- | --- | --- |
| Confirm release branch/build under validation | `TBD` | `TBD` |  |
| Confirm production vs staging target for signoff run | `TBD` | `TBD` |  |
| Assign all owners in tracker and checklist | `TBD` | `TBD` |  |
| Confirm scope decisions needed today | `TBD` | `TBD` |  |
| Confirm evidence storage locations | `TBD` | `TBD` |  |

Stop condition:
- do not proceed until owners and scope are clear

## Phase 1: Scope And Platform Gate

Goal:
- decide what is in release
- prove the platform is usable

Steps:

| Step | Owner | Command / Method | Output |
| --- | --- | --- | --- |
| Decide GST reconciliation rollout posture | `TBD` | Release lead + business review | `Full`, `Controlled Rollout`, or `Deferred` |
| Decide commerce / retail / subscriptions / sales legacy import scope | `TBD` | Release lead review | Explicit `Release` or `Deferred` per item |
| Verify env vars, migrations, and config | `TBD` | Infra / backend review | Pass / fail with notes |
| Run platform smoke | `TBD` | `npm run test:launch-commercial-smoke` | HTML report + artifacts |
| Verify session expiry and unauthorized redirect behavior | `TBD` | Manual | Notes / recording |
| Verify RBAC for critical module entry points | `TBD` | Manual + targeted suites | Notes / report |

Go checkpoint:
- auth works
- onboarding/auth smoke passes
- critical routing is usable
- release scope is frozen

No-go examples:
- login instability
- wrong environment config
- broken protected routes
- unresolved scope ambiguity for critical modules

## Phase 2: Commercial Core Gate

Goal:
- validate the most business-critical operational flows first

Run order:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:payment:signoff
npm run test:purchase:signoff
npm run test:sales:signoff
```

Manual follow-ups:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Validate receipt voucher ledger and receivable impact | `TBD` | Manual transaction + report check | Notes |
| Validate payment voucher ledger and payable impact | `TBD` | Manual transaction + report check | Notes |
| Validate journal / bank / cash voucher ledger impact | `TBD` | Manual posting check | Notes |
| Review purchase print outputs | `TBD` | Manual | Captures |
| Review sales print outputs | `TBD` | Manual | Captures |
| Validate purchase and sales reconciliation downstream | `TBD` | Manual + existing smoke evidence | Notes |

Go checkpoint:
- vouchers, purchase, and sales signoff suites pass
- no posting or reconciliation mismatch
- print outputs are acceptable

No-go examples:
- post/unpost failure
- incorrect outstanding reduction
- broken tax or policy behavior
- report totals diverging from transactions

## Phase 3: Reporting And Compliance Gate

Goal:
- prove the reporting layer is trustworthy after transaction validation

Run order:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:reports-regression
```

Manual follow-ups:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Validate trial balance, ledger, P&L, balance sheet totals | `TBD` | Manual | Notes |
| Validate payables report totals and drilldowns | `TBD` | Manual | Notes |
| Validate receivables report totals and drilldowns | `TBD` | Manual | Notes |
| Validate GST report buckets and filters | `TBD` | Manual | Notes |
| Validate GST / statutory exports | `TBD` | Manual | Output captures |
| Validate compliance exception and filing-readiness views | `TBD` | Manual | Notes |
| Validate TCS filing posture and GST-TDS / withholding chain | `TBD` | Manual | Notes |

Go checkpoint:
- financial and compliance regression passes
- business owners accept totals and exports

No-go examples:
- totals mismatch
- missing filters or broken drilldowns
- unusable exports
- incorrect tax bucket classification

## Phase 4: Bank Reconciliation Gate

Goal:
- close one of the highest-risk operational control areas explicitly

Suggested sequence:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Import and validate statement | `TBD` | Manual + browser | Notes |
| Auto-match and manual match | `TBD` | Manual live mutation | Notes |
| Group match / partial match / unmatch / exceptions | `TBD` | Manual live mutation | Notes |
| Create voucher from bank row | `TBD` | Manual live mutation | Voucher evidence |
| Validate run actions and reload persistence | `TBD` | Manual | Notes |
| Validate unmatched / BRS / audit / downstream parity | `TBD` | Manual + existing P1 integrity suite | Notes |

Go checkpoint:
- reconciliation actions persist correctly
- downstream reports align after mutation

No-go examples:
- mutation submits fail
- reload loses state
- voucher creation corrupts reconciliation posture
- report parity breaks

## Phase 5: Inventory, Manufacturing, Assets Gate

Goal:
- validate operational support modules before final integrated signoff

Steps:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Validate catalog propagation into transactions | `TBD` | Manual + relevant suites | Notes |
| Validate transfer and adjustment flows | `TBD` | Manual + inventory suites | Notes |
| Validate inventory report parity | `TBD` | Manual | Notes |
| Validate manufacturing workspaces | `TBD` | Manual + P1 suites | Notes |
| Validate manufacturing quantity/cost outputs | `TBD` | Manual | Notes |
| Validate asset purchase-to-asset and depreciation behavior | `TBD` | Manual + existing evidence | Notes |

Go checkpoint:
- no critical stock, costing, or asset lifecycle issue remains

## Phase 6: Payroll And HRMS Gate

Goal:
- prove payroll is operationally safe for release scope

Run order:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:payroll-rbac
npm run test:payroll
```

Manual follow-ups:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Validate payroll run lifecycle | `TBD` | Manual | Notes |
| Validate posting preview / posting readiness | `TBD` | Manual | Notes |
| Validate ESS scope | `TBD` | Manual | Notes |
| Validate approvals and policies | `TBD` | Manual | Notes |
| Confirm HRMS scope and validate if included | `TBD` | Manual | Notes |

Go checkpoint:
- payroll run and access controls behave correctly
- posting readiness is accepted

## Phase 7: Support, Observability, And Rollback Gate

Goal:
- clear the biggest current blocker before final release decision

Steps:

| Step | Owner | Method | Output |
| --- | --- | --- | --- |
| Trigger and verify app error capture | `TBD` | Manual | Logs / screenshots |
| Review audit logging for critical actions | `TBD` | Manual | Notes |
| Review support diagnostics and incident workflow | `TBD` | Manual | Notes |
| Review rollback plan | `TBD` | Manual | Notes |
| Review hotfix path and escalation chain | `TBD` | Manual | Notes |

Go checkpoint:
- support team can observe, diagnose, and respond
- rollback is understood and accepted

No-go examples:
- no reliable error capture
- no rollback clarity
- no support coverage for first-day incidents

## Phase 8: Final Decision Meeting

Required attendees:

- release lead
- QA lead
- backend lead
- frontend lead
- finance/business signoff
- infra/support owner

Agenda:

| Topic | Owner | Result |
| --- | --- | --- |
| Review critical failures | `TBD` |  |
| Review accepted conditions | `TBD` |  |
| Confirm deferred scope | `TBD` |  |
| Confirm rollback and support readiness | `TBD` |  |
| Record final `Go` or `No-Go` | `TBD` |  |

## Fast Start Version

If the team needs the shortest actionable sequence:

1. Freeze scope and assign owners.
2. Run `npm run test:launch-commercial-smoke`.
3. Run `npm run test:payment:signoff`.
4. Run `npm run test:purchase:signoff`.
5. Run `npm run test:sales:signoff`.
6. Run `npm run test:reports-regression`.
7. Run `npm run test:payroll-rbac`.
8. Run `npm run test:payroll`.
9. Do manual signoff for posting, reports, exports, bank reco, observability, and rollback.
10. Hold final go/no-go meeting.
