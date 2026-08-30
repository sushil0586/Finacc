# Finacc Production Go / No-Go Tracker

Date: 2026-08-21

## Purpose

This document is the final execution tracker for production release signoff.

Use it to:

- assign owners
- execute validation in the right order
- record evidence
- identify blockers
- drive the final go / no-go decision

## Status Values

- `Not Started`
- `In Progress`
- `Passed`
- `Passed With Conditions`
- `Blocked`
- `Deferred`
- `Failed`

## Final Decision Rule

Production should only be marked `Go` when:

1. all release-critical tracks are `Passed` or `Passed With Conditions`
2. every `Passed With Conditions` item has an explicit accepted risk note
3. no unresolved `Blocked` or `Failed` item remains in release scope
4. rollback and support readiness are confirmed

## Release Decision Summary

| Decision Area | Owner | Status | Notes |
| --- | --- | --- | --- |
| Overall release decision | `TBD` | `In Progress` | Repo evidence reviewed; live execution and final business signoff still pending |
| Commercial core | `TBD` | `In Progress` | Strongest existing automation footprint and signoff script support |
| Reporting and compliance | `TBD` | `In Progress` | Broad browser coverage exists; totals and export signoff still pending |
| Inventory and manufacturing | `TBD` | `In Progress` | Real coverage exists, but live quantitative validation still pending |
| Payroll and HRMS | `TBD` | `In Progress` | Payroll evidence is meaningful; HRMS remains lighter |
| Platform and access | `TBD` | `In Progress` | Auth, onboarding, and RBAC evidence exists from code and test suites |
| Observability and rollback | Infra / Support / Release lead | `Passed With Conditions` | Automated error/audit/config evidence is green; final go still requires production security settings, named support owner, and rollback walkthrough signoff |

## Track 1: Platform And Access

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Login, auth, route protection | `TBD` | `npm run test:launch-commercial-smoke` from `finacc-ui-tests` | Existing smoke script plus auth P0 suites | `In Progress` | Yes | Script exists and auth coverage is present; rerun needed in release env |
| Registration and onboarding | `TBD` | Included in `test:launch-commercial-smoke` | Existing script plus onboarding P0 suites | `In Progress` | Yes | Repo evidence is strong; live rerun pending |
| Entity scope behavior | `TBD` | Manual plus smoke confirmation across at least purchase and sales | Existing auth/entity integration suite plus manual notes needed | `In Progress` | Yes | Cross-module live scope verification still needed |
| RBAC for critical modules | `TBD` | Manual role-matrix pass plus `tests/p0/reports-rbac.p0.spec.ts` and `test:payroll-rbac` | Existing RBAC suites | `In Progress` | Yes | Need explicit role-matrix execution evidence |
| Session expiry and unauthorized redirects | `TBD` | Manual in release environment | Manual evidence required | `Not Started` | Yes | No trustworthy repo-only proof |

## Track 2: Commercial Core

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Receipt voucher core flow | `TBD` | `tests/p0/receipt-voucher.p0.spec.ts` and `tests/p1/receipt-voucher.p1.spec.ts` | Existing P0/P1 suites and artifacts under `test-results-p0-full-run` / `test-results-p1` | `In Progress` | Yes | Strong evidence exists; rerun and report parity check still needed |
| Payment and voucher stack | `TBD` | `npm run test:payment:signoff` | Existing signoff command definitions | `In Progress` | Yes | Command path is ready; release-env execution pending |
| Purchase signoff | `TBD` | `npm run test:purchase:signoff` | Existing signoff command definitions and large P1 artifact set | `In Progress` | Yes | One of the strongest release-ready areas |
| Sales signoff | `TBD` | `npm run test:sales:signoff` | Existing signoff command definitions and large P1 artifact set | `In Progress` | Yes | One of the strongest release-ready areas |
| Purchase and sales downstream reconciliation | `TBD` | Included in `test:launch-commercial-smoke` plus targeted P1 reconciliation rerun | Existing reconciliation suites named in smoke bundle | `In Progress` | Yes | Live rerun still required |
| Journal, bank, and cash voucher ledger validation | `TBD` | Manual posting and report verification | Manual evidence required | `Not Started` | Yes | Shared voucher automation exists, but ledger proof must be manual/live |
| Print and export sanity check | `TBD` | Manual output validation for purchase and sales print flows | Existing print suites plus manual output evidence needed | `In Progress` | Yes | Environment-sensitive final validation remains |
| Legacy import sanity check | `TBD` | Manual import of representative sample for enabled import flows | Purchase legacy import docs and suites exist | `In Progress` | Conditional | Sales legacy import still needs explicit scope call |

## Track 3: Reporting And Compliance

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Financial report regression | `TBD` | `npm run test:reports-regression` | Existing command and multiple financial/compliance/bank-reco integrity suites | `In Progress` | Yes | Release-env rerun pending |
| Financial hub live totals sanity check | `TBD` | Manual check of trial balance, ledger, P&L, balance sheet | Existing financial parity and integrity suites plus manual notes needed | `In Progress` | Yes | Totals signoff must be manual/live |
| Payables report sanity check | `TBD` | Manual plus P1 report/browser suites | Existing AP aging, vendor outstanding, ledger, settlement suites | `In Progress` | Yes | Manual totals confirmation still needed |
| Receivables report sanity check | `TBD` | Manual plus P1 report/browser suites | Existing receivables browser, filter, data-integrity, and cross-report suites | `In Progress` | Yes | Manual totals confirmation still needed |
| GST report sanity check | `TBD` | Manual plus `tests/p1/gst-report-browser.p1.spec.ts` and related suites | Existing GST browser and exception suites | `In Progress` | Yes | Export and bucket-total signoff still needed |
| Compliance browser and parity check | `TBD` | Manual plus compliance-related P1 suites | Existing compliance browser and performance suites | `In Progress` | Yes | Filing-readiness still needs manual signoff |
| GST and statutory export validation | `TBD` | Manual export check | Manual evidence required | `Not Started` | Yes | Final artifact validation cannot be inferred from repo only |
| TCS browser and filing posture | `TBD` | Manual plus TCS P1 suites | Existing TCS browser, drilldown, statutory, export suites | `In Progress` | Yes | Filing posture requires business confirmation |
| GST-TDS and withholding chain validation | `TBD` | Manual end-to-end config to report check | Partial repo evidence only | `Not Started` | Yes | One of the thinner release-proof areas |

## Track 4: Bank Reconciliation

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Import, preview, validate, workspace handoff | `TBD` | Bank reco P1 suites plus manual live run | Existing workflow and browser suites | `In Progress` | Yes | Strong evidence exists, but release rerun pending |
| Auto-match and manual match | `TBD` | Manual live mutation plus existing suites | Existing API/browser evidence plus manual notes needed | `In Progress` | Yes | Live mutation closure still critical |
| Group match, partial match, unmatch, exception flows | `TBD` | Manual live mutation pass | Existing gap plan identifies these as high-risk | `Not Started` | Yes | Still a focused release risk |
| Voucher creation from bank row | `TBD` | Manual live run and downstream verification | Existing API evidence plus manual proof needed | `Not Started` | Yes | Needs explicit live proof |
| Run actions and reload persistence | `TBD` | Manual live validation | Manual evidence required | `Not Started` | Yes | Known risk from prior gap analysis |
| Downstream report parity | `TBD` | `tests/p1/bank-reco-data-integrity-live.p1.spec.ts` plus manual check | Existing data-integrity suite | `In Progress` | Yes | Manual parity signoff still needed |

## Track 5: Inventory, Manufacturing, Assets

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Catalog and product propagation | `TBD` | Relevant P2 suites plus manual propagation check | Existing catalog P2 suites | `In Progress` | Yes | Manual propagation proof still required |
| Inventory transfer and adjustment | `TBD` | Inventory P1 CRUD suites plus manual stock effect check | Existing inventory ops suites | `In Progress` | Yes | Stock effect signoff pending |
| Inventory report parity | `TBD` | Inventory P1 reporting suites plus manual totals check | Existing inventory report matrix suites | `In Progress` | Yes | Manual totals signoff pending |
| Manufacturing workspace sanity check | `TBD` | Manufacturing P1 suites plus manual lifecycle review | Existing manufacturing browser and visual suites | `In Progress` | Yes | Real coverage exists; lifecycle signoff pending |
| Manufacturing cost / quantity output check | `TBD` | Manual release-scope verification | Manual evidence required | `Not Started` | Yes | Key quantitative release risk |
| Asset module sanity check | `TBD` | Asset P1 suites plus manual purchase-to-asset and depreciation check | Existing asset purchase flow audit evidence | `In Progress` | Yes | Depreciation/report signoff still needed |

## Track 6: Payroll And HRMS

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Payroll RBAC | `TBD` | `npm run test:payroll-rbac` | Existing command and suite | `In Progress` | Yes | Release-env rerun pending |
| Payroll suite | `TBD` | `npm run test:payroll` | Existing command and suite | `In Progress` | Yes | Release-env rerun pending |
| Payroll run and posting preview | `TBD` | Manual live verification | Payroll docs and surfaces exist; manual proof needed | `Not Started` | Yes | Core live signoff item |
| Payroll ESS validation | `TBD` | Manual role-based validation | Frontend breadth exists; manual proof needed | `Not Started` | Conditional |  |
| Payroll approvals and policies | `TBD` | Manual approval workflow validation | Surfaces exist; proof is lighter | `Not Started` | Conditional |  |
| HRMS release-scope validation | `TBD` | Manual scope confirmation and focused validation | Repo evidence is lighter | `Not Started` | Conditional | Explicit release-scope call needed |

## Track 7: Support, Observability, And Rollback

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Application error capture works | Support / backend | `./venv/bin/python manage.py test errorlogger.tests --verbosity=2 --keepdb` plus stage-only support observation | Error logger contract included in the `88 OK` operational suite | `Passed With Conditions` | Yes | Production condition: support must observe one safe stage/prod-like error in the configured logging sink before final go |
| Audit logging is usable for critical actions | QA / support | `./venv/bin/python manage.py test rbac.tests.test_user_access_admin bank_reco.matching_api_tests --verbosity=2 --keepdb` plus manual audit-view review | RBAC admin audit and Bank Reco audit trail contracts included in the `88 OK` operational suite | `Passed With Conditions` | Yes | Production condition: capture RBAC and Bank Reco audit screenshots/exports from release environment |
| Support diagnostics are sufficient | Support owner | Runbook and SOP review | `docs/qa/release-execution-runbook-2026-08-21.md`, `docs/reports/compliance_ops_monitoring_sop.md`, `docs/reports/compliance_post_go_live_support_sop.md` | `Passed With Conditions` | Yes | Production condition: assign named incident owner and confirm ticket/channel coverage for first release window |
| Rollback path is documented and understood | Release lead / infra | Walk rollback checklist in release runbook | Rollback checklist added to `docs/qa/release-execution-runbook-2026-08-21.md` | `Passed With Conditions` | Yes | Production condition: record backup/artifact versions and complete rollback walkthrough before deploy |
| Hotfix path and escalation chain are clear | Release lead / support | Walk hotfix checklist in release runbook | Hotfix checklist added to `docs/qa/release-execution-runbook-2026-08-21.md` | `Passed With Conditions` | Yes | Production condition: name severity owner, communication owner, approval path, and minimum test slice |

## Track 8: Scope Decisions

| Item | Owner | Decision Needed | Status | Notes |
| --- | --- | --- | --- | --- |
| GST reconciliation | `TBD` | Full production vs controlled rollout / pilot | `In Progress` | Existing docs indicate pilot-style maturity; do not assume broad go-live by default |
| Commerce | `TBD` | Included in release or deferred | `Not Started` | Needs explicit scope decision |
| Retail | `TBD` | Included in release or deferred | `Not Started` | Needs explicit scope decision |
| Subscriptions | `TBD` | Included in release or deferred | `Not Started` | More planning-oriented than proven release module |
| Sales legacy import | `TBD` | Included in release or deferred | `Not Started` | Proof is much lighter than purchase legacy import |

## Command Reference

Run from `/Users/ansh/Documents/finacc-ui-tests` unless stated otherwise.

| Purpose | Command |
| --- | --- |
| P0 baseline | `npm run test:p0` |
| Commercial smoke | `npm run test:launch-commercial-smoke` |
| Purchase signoff | `npm run test:purchase:signoff` |
| Sales signoff | `npm run test:sales:signoff` |
| Payment signoff | `npm run test:payment:signoff` |
| Commercial signoff bundle | `npm run test:commercial:signoff` |
| Reports regression | `npm run test:reports-regression` |
| Payroll | `npm run test:payroll` |
| Payroll RBAC | `npm run test:payroll-rbac` |

## Evidence Index

| Track | Evidence Location | Notes |
| --- | --- | --- |
| Automated test output | `finacc-ui-tests/playwright-report` | Latest HTML report after rerun |
| Test artifacts | `finacc-ui-tests/test-results*` | Existing artifact directories include `test-results-p0-full-run` and `test-results-p1` |
| Manual signoff notes | `Finacc/docs/qa/production-go-no-go-tracker-2026-08-21.md` | Record release meeting decisions, accepted conditions, and manual pass/fail notes here |
| Release screenshots / exports | `/Users/ansh/Documents/finacc-ui-tests/test-results*` plus linked manual captures | Store automated artifacts in Playwright output; link any manual business-format captures in this tracker |
| Rollback and support notes | `Finacc/docs/qa/release-execution-runbook-2026-08-21.md` and this tracker | Runbook now contains rollback/hotfix checklists; tracker records final owner/signoff evidence |

## Final Go / No-Go Meeting Notes

| Topic | Summary |
| --- | --- |
| Open blockers | No Track 7 blocker remains after operational-readiness documentation and focused backend evidence; release-wide blockers still depend on final live reruns and manual signoff. |
| Accepted release conditions | Track 7 is `Passed With Conditions`: production security settings, named support owner, support-observed error capture, audit-view screenshots/exports, backup/artifact version recording, and rollback/hotfix walkthrough must be completed before final go. |
| Deferred scope |  |
| Rollback readiness | Runbook checklist exists; final go requires release-lead/infra walkthrough and recorded backup/artifact versions. |
| Support coverage | SOPs and diagnostics path exist; final go requires named first-window support owner and ticket/channel confirmation. |
| Final decision |  |
