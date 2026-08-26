# Finacc Release-Day Checklist

Date: 2026-08-21

## Purpose

This is the short operational checklist for release day.

Use this together with:

- [Production Go / No-Go Tracker](./production-go-no-go-tracker-2026-08-21.md)
- [Production Release Granular Verification Matrix](./production-release-granular-verification-matrix-2026-08-21.md)

This checklist is intentionally short. The detailed tracker remains the source of truth.

## Final Rule

Do not release if any `Critical` item below is unresolved.

## Section 1: Scope Decision

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Confirm release scope is frozen | Critical | `TBD` | `TBD` |  |
| Decide `GST reconciliation`: full production vs controlled rollout | Critical | `TBD` | `TBD` |  |
| Decide `commerce`: release vs defer | High | `TBD` | `TBD` |  |
| Decide `retail`: release vs defer | High | `TBD` | `TBD` |  |
| Decide `subscriptions`: release vs defer | High | `TBD` | `TBD` |  |
| Decide `sales legacy import`: release vs defer | High | `TBD` | `TBD` |  |

## Section 2: Platform Readiness

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Production env vars and config verified | Critical | `TBD` | `TBD` |  |
| DB migrations reviewed and safe | Critical | `TBD` | `TBD` |  |
| Auth, onboarding, and protected routing smoke passed | Critical | `TBD` | `TBD` | Use `npm run test:launch-commercial-smoke` |
| RBAC for critical modules signed off | Critical | `TBD` | `TBD` |  |
| Session expiry and unauthorized behavior checked | High | `TBD` | `TBD` |  |

## Section 3: Commercial Core

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Receipt voucher validation passed | Critical | `TBD` | `TBD` |  |
| Payment and voucher validation passed | Critical | `TBD` | `TBD` | Use `npm run test:payment:signoff` |
| Purchase validation passed | Critical | `TBD` | `TBD` | Use `npm run test:purchase:signoff` |
| Sales validation passed | Critical | `TBD` | `TBD` | Use `npm run test:sales:signoff` |
| Purchase and sales downstream reconciliation signed off | Critical | `TBD` | `TBD` |  |
| Manual print and export output reviewed | Critical | `TBD` | `TBD` |  |
| Ledger impact sanity check completed for voucher stack | Critical | `TBD` | `TBD` |  |

## Section 4: Reporting And Compliance

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Financial report regression passed | Critical | `TBD` | `TBD` | Use `npm run test:reports-regression` |
| Financial hub totals signed off | Critical | `TBD` | `TBD` |  |
| Payables and receivables report sanity signed off | Critical | `TBD` | `TBD` |  |
| GST reports signed off | Critical | `TBD` | `TBD` |  |
| Compliance browser and parity signed off | High | `TBD` | `TBD` |  |
| GST and statutory exports reviewed | Critical | `TBD` | `TBD` |  |
| TCS filing posture reviewed | High | `TBD` | `TBD` |  |
| GST-TDS and withholding chain reviewed | Critical | `TBD` | `TBD` |  |

## Section 5: Inventory, Manufacturing, Assets

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Catalog propagation sanity check passed | High | `TBD` | `TBD` |  |
| Inventory transfer and adjustment sanity passed | High | `TBD` | `TBD` |  |
| Inventory report parity signed off | High | `TBD` | `TBD` |  |
| Manufacturing workspace sanity check passed | High | `TBD` | `TBD` |  |
| Manufacturing quantity / cost outputs reviewed | Critical | `TBD` | `TBD` |  |
| Asset module sanity and depreciation checks passed | High | `TBD` | `TBD` |  |

## Section 6: Bank Reconciliation

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Import to workspace path signed off | Critical | `TBD` | `TBD` |  |
| Match and exception flows signed off | Critical | `TBD` | `TBD` |  |
| Voucher creation from bank row signed off | Critical | `TBD` | `TBD` |  |
| Run actions and reload persistence signed off | Critical | `TBD` | `TBD` |  |
| Downstream report parity signed off | Critical | `TBD` | `TBD` |  |

## Section 7: Payroll And HRMS

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Payroll RBAC passed | Critical | `TBD` | `TBD` | Use `npm run test:payroll-rbac` |
| Payroll suite passed | Critical | `TBD` | `TBD` | Use `npm run test:payroll` |
| Payroll run and posting preview signed off | Critical | `TBD` | `TBD` |  |
| Payroll ESS reviewed for release scope | High | `TBD` | `TBD` |  |
| Payroll approvals and policies reviewed | High | `TBD` | `TBD` |  |
| HRMS release scope confirmed and signed off | High | `TBD` | `TBD` |  |

## Section 8: Support And Rollback

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Application error capture verified | Critical | `TBD` | `TBD` |  |
| Audit logging for critical actions verified | Critical | `TBD` | `TBD` |  |
| Support diagnostics and runbook reviewed | Critical | `TBD` | `TBD` |  |
| Rollback path reviewed and accepted | Critical | `TBD` | `TBD` |  |
| Hotfix path and escalation chain confirmed | Critical | `TBD` | `TBD` |  |

## Section 9: Final Meeting

| Item | Priority | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| Open blockers reviewed | Critical | `TBD` | `TBD` |  |
| Accepted release conditions documented | Critical | `TBD` | `TBD` |  |
| Deferred scope documented | Critical | `TBD` | `TBD` |  |
| Final go / no-go decision recorded | Critical | `TBD` | `TBD` |  |

## Quick Commands

Run from `/Users/ansh/Documents/finacc-ui-tests`.

```bash
npm run test:launch-commercial-smoke
npm run test:payment:signoff
npm run test:purchase:signoff
npm run test:sales:signoff
npm run test:reports-regression
npm run test:payroll-rbac
npm run test:payroll
```
