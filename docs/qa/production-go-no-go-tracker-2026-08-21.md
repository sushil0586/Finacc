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
| Overall release decision | `TBD` | `Passed With Conditions` for non-payroll scope; `Blocked` if Payroll is in scope | Geography blocker is remediated, latest clean-start full P0 stage run ended `248 passed`, `30 skipped`, `0 failed` in `1.2h`, and Bank Reco matched-environment mutation/integrity proof is closed; final go still needs Payroll entitlement/seed decision if Payroll is in scope plus production-owner operational acceptance |
| Commercial core | `TBD` | `Passed With Conditions` | Full P0 commercial paths are stage-green after launch seed and route/fixture hardening; manual business-format print/export/reconciliation signoff remains |
| Reporting and compliance | `TBD` | `Passed With Conditions` | Stage-valid financial/compliance subset and Bank Reco browser/mutation/integrity evidence are green; manual totals/export confirmation remains |
| Inventory and manufacturing | `TBD` | `In Progress` | Real coverage exists, but live quantitative validation still pending |
| Payroll and HRMS | `TBD` | `Blocked` | Payroll routes are currently blocked on `Mehak-T` by `feature_payroll` subscription entitlement; HRMS remains lighter |
| Platform and access | `TBD` | `Passed With Conditions` | Auth, onboarding, subscription, dashboard, RBAC, and full P0 stage paths are green; final owner review still required |
| Observability and rollback | Infra / Support / Release lead | `Passed With Conditions` | Stage health, migration check, backup creation/readability, log scan, audit/error visibility, and local operational contracts are green; final go still requires production security settings, named support owner, SMTP/invite inbox proof, and rollback/hotfix walkthrough signoff |

## Track 1: Platform And Access

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Login, auth, route protection | `TBD` | `tests/p0/auth*.p0.spec.ts` plus full P0 stage run | Clean full P0 stage run: `248 passed`, `30 skipped`, `0 failed`; auth/entity focused proof: `6 passed` | `Passed` | No | Login, route protection, logout, session reload, and cookie-backed auth-hint recovery are green on stage |
| Registration and onboarding | `TBD` | Included in P0 plus stage onboarding P1 rerun | Stage onboarding P1 after quota/geography remediation: `7 passed`, `1 skipped`; public registration P0 included in clean full P0 | `Passed With Conditions` | No | Fresh create-and-activate and added-branch paths are green; capped quota denial remains a controlled alternate-tenant branch |
| Entity scope behavior | `TBD` | Full P0 plus smoke confirmation across purchase and sales | `Mehak-T` full P0 stage run green; `Ritikasharma` entity smoke `4 passed` | `Passed With Conditions` | No | Keep exact displayed entity casing in env; manual scope spot-check can be attached at final go |
| RBAC for critical modules | `TBD` | `tests/p0/reports-rbac.p0.spec.ts`, payroll RBAC, admin/RBAC P1 | Full P0 includes restricted RBAC matrix; admin/RBAC stage gate `10 passed`; payroll RBAC included in P0 | `Passed With Conditions` | No | Automated matrix is green; manual role-owner acknowledgement still useful |
| Session expiry and unauthorized redirects | `TBD` | Auth P0 and subscription unauthorized P0 | Included in clean full P0 stage run | `Passed` | No | Expired session, unauthorized feature context, and blocked-route recovery are covered |

## Track 2: Commercial Core

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Receipt voucher core flow | `TBD` | `tests/p0/receipt-voucher.p0.spec.ts` and `tests/p1/receipt-voucher.p1.spec.ts` | Receipt P0 included in clean full P0 stage run; focused receipt cleanup `3 passed` with sales policy canary | `Passed With Conditions` | No | Core receipt browser workflow is green; keep report parity in final business signoff |
| Payment and voucher stack | `TBD` | `npm run test:payment:signoff` plus P0 voucher suite | Payment/voucher paths included in clean full P0; compact voucher/payables proof `41 passed`; payment tail rerun `12 passed` | `Passed With Conditions` | No | Payment open-item/advance and TDS paths are stage-green; manual settlement report signoff remains |
| Purchase signoff | `TBD` | `npm run test:purchase:signoff` plus P0/P1 focused runs | Purchase P0 included in clean full P0; purchase note cluster `7 passed`; purchase P1 focused cleanup green | `Passed With Conditions` | No | Strong release-ready evidence; manual print/export sample still needed |
| Sales signoff | `TBD` | `npm run test:sales:signoff` plus P0/TCS focused runs | Sales P0 included in clean full P0; compact sales smoke `9 passed`, `1 skipped`; Sales TCS full flow `9 passed` | `Passed With Conditions` | No | Geography/customer/product blocker is remediated; manual print/export sample still needed |
| Purchase and sales downstream reconciliation | `TBD` | Included in `test:launch-commercial-smoke` plus targeted P1 reconciliation rerun | Sales/purchase source-to-report reconciliation focused evidence is green | `Passed With Conditions` | No | Keep manual business totals spot-check before final go |
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
| Compliance browser and parity check | `TBD` | Manual plus compliance-related P1 suites | Stage-valid financial/compliance subset: `13 passed`, `5 skipped`, `0 failed`; Sales TCS full flow `9 passed`; Bank Reco matched-environment browser/mutation/integrity proof is green | `Passed With Conditions` | No | Geography blocker is closed; remaining skips are live-data availability branches, not active red failures |
| GST and statutory export validation | `TBD` | Manual export check | Manual evidence required | `Not Started` | Yes | Final artifact validation cannot be inferred from repo only |
| TCS browser and filing posture | `TBD` | Manual plus TCS P1 suites | Existing TCS browser, drilldown, statutory, export suites | `In Progress` | Yes | Filing posture requires business confirmation |
| GST-TDS and withholding chain validation | `TBD` | Manual end-to-end config to report check | Partial repo evidence only | `Not Started` | Yes | One of the thinner release-proof areas |

## Track 4: Bank Reconciliation

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Import, preview, validate, workspace handoff | `TBD` | Bank reco P1 browser subset plus matched-environment stage run | Stage import lifecycle `8 passed`; full browser surface `23 passed`, `7 skipped`, `0 failed`; workflow matrix `4 passed`, `7 skipped`, `0 failed` | `Passed With Conditions` | No | Dashboard, import setup, invalid mapping, duplicate-period guidance, archived import lock, workspace shell/context switching, timing, visual compactness, and workflow handoff are green; skips are conditional live-state/action-availability branches |
| Auto-match and manual match | `TBD` | Remote-stage-aware Playwright mutation suite plus backend guard | `bank-reco-live-mutations.p1.spec.ts` completed `10 passed`; local backend Bank Reco API guard completed `53 OK` | `Passed With Conditions` | No | Remote-stage Django shell helper now seeds stage safely over SSH; manual/group/match cleanup paths are covered in focused browser/API evidence |
| Group match, partial match, unmatch, exception flows | `TBD` | Remote-stage-aware Playwright mutation suite | Live mutations `10 passed`; workflow matrix including former local-shell case has `0 failed` | `Passed With Conditions` | No | Group, partial, exception, cleanup, stale replay, and mark-reconciled paths are stage-covered; keep conditional sparse-data skips in final watchlist |
| Voucher creation from bank row | `TBD` | Remote-stage-aware Playwright mutation suite plus backend guard | Live mutation suite includes voucher creation from unmatched bank lines; backend guard `53 OK` | `Passed With Conditions` | No | Voucher creation and duplicate-voucher prevention are covered; production-scale/manual finance review remains useful |
| Run actions and reload persistence | `TBD` | Bank Reco workflow/browser packs | Full browser surface `23 passed`, `7 skipped`, `0 failed`; live mutations `10 passed` | `Passed With Conditions` | No | Reload-sensitive actions are no longer blocked by local-vs-stage seeding; long marathon browser pressure remains non-blocking soak risk |
| Downstream report parity | `TBD` | Remote-stage-aware data-integrity suite | `bank-reco-data-integrity-live.p1.spec.ts` completed `6 passed`; final stage audit `conflict_count=0` | `Passed With Conditions` | No | BRS, audit trail, unmatched bank/books reports, run counts, and filtered report checks are stage-green for current seeded scale |

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
| Payroll suite | `TBD` | `npm run test:payroll` | Latest stage smoke grep `PAYROLL-00[1-4]` produced `1 passed`, `4 skipped`, `0 failed` because `feature_payroll` is disabled for `Mehak-T`; deeper workflow tests still need remote-safe or matched-environment seed setup | `Blocked` | Yes | Enable Payroll for the launch tenant or use a payroll-enabled stage tenant, then make payroll P1 seed setup stage-aware or run in matched backend/browser environment before final signoff |
| Payroll run and posting preview | `TBD` | Manual live verification | Payroll docs and surfaces exist; manual proof needed | `Not Started` | Yes | Core live signoff item |
| Payroll ESS validation | `TBD` | Manual role-based validation | Frontend breadth exists; manual proof needed | `Not Started` | Conditional |  |
| Payroll approvals and policies | `TBD` | Manual approval workflow validation | Surfaces exist; proof is lighter | `Not Started` | Conditional |  |
| HRMS release-scope validation | `TBD` | Manual scope confirmation and focused validation | Repo evidence is lighter | `Not Started` | Conditional | Explicit release-scope call needed |

## Track 7: Support, Observability, And Rollback

| Check | Owner | Command / Method | Evidence | Status | Blocking | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Stage deploy health and migration readiness | Infra / backend | Stage SSH health probe, `manage.py check`, `migrate --check --noinput`, `nginx -t`, service status | Stage commit `936dce13`; Django check clean; migration check clean; nginx config valid; `finacc-gunicorn` and `nginx` active | `Passed With Conditions` | No | Remote `git status --short` is noisy because tracked legacy pycache/old environment files appear deleted; use commit hash and deployed artifact capture for release evidence |
| Production security settings | Infra / backend | Stage `manage.py check --deploy`, settings probe, and release env audit | `check --deploy` returns `0` errors but warns on HSTS, HTTPS redirect, insecure-looking `SECRET_KEY`, secure session cookie, secure CSRF cookie, and `DEBUG=True`; stage settings show `DEBUG=True`, secure cookie flags false, HSTS `0`; local `audit_release_environment` focused tests passed `5 OK`; combined operational guard passed `93 OK`; simulated hardened env audit returned `ready=true`, `10` pass, `0` fail, `0` warn | `Passed With Conditions` | Yes | After deployment, run `venv/bin/python manage.py audit_release_environment --strict --require-email`; add `--edge-https-redirect --edge-hsts` only if nginx/load balancer owns those controls. Production must pass or explicitly accept each failed security item before final go |
| Application error capture works | Support / backend | Local contract plus stage error table visibility | Local `venv/bin/python manage.py test errorlogger.tests rbac.tests.test_api rbac.tests.test_user_access_admin bank_reco.matching_api_tests --keepdb --verbosity=1` completed `88 OK`; stage `errorlogger.ErrorLog` has `7000` rows and `234` in the last 24h | `Passed With Conditions` | Conditional | Recent stage sample includes expected validation rows plus historical captured defects such as duplicate numbering, stale subentity mismatch, prior purchase meta `NameError`, and prior GST-TDS export sort `TypeError`; last 30-minute gunicorn exception scan was empty. Production condition: support must observe one safe stage/prod-like error in the configured logging sink/admin before final go |
| Audit logging is usable for critical actions | QA / support | Local audit contracts plus stage audit table visibility | Stage has recent `Authentication.AuthAuditLog` (`140` in 24h), `bank_reco.BankReconciliationAuditLog` (`106` in 24h), and generic `auditlogger.AuditLog` (`56028` in 24h); local operational contracts passed `88 OK` | `Passed With Conditions` | Conditional | Production condition: capture RBAC and Bank Reco audit screenshots/exports from release environment |
| Support diagnostics are sufficient | Support owner | Runbook and SOP review | `docs/qa/release-execution-runbook-2026-08-21.md`, `docs/reports/compliance_ops_monitoring_sop.md`, `docs/reports/compliance_post_go_live_support_sop.md`; last 30-minute gunicorn exception scan was empty | `Passed With Conditions` | Conditional | Production condition: assign named incident owner and confirm ticket/channel coverage for first release window |
| Rollback path is documented and understood | Release lead / infra | Walk rollback checklist plus stage backup/readability proof | Custom-format stage backup created at `/home/ubuntu/Finacc/backups/stage_pre_release_20260903T101337Z.dump` with size `11241436` bytes; `pg_restore -l` successfully listed TOC entries; frontend artifact `/var/www/accerio` is `383M`, staticfiles `18M`, media `11M` | `Passed With Conditions` | Conditional | Production condition: release lead/infra must accept backup location/retention, artifact restore path, and post-rollback smoke checklist |
| Hotfix path and escalation chain are clear | Release lead / support | Walk hotfix checklist in release runbook | Hotfix checklist exists; current local operational safety net `88 OK`; stage commit recorded as `936dce13fc8d36230bafa3aa626fff2a93ed91f2` | `Passed With Conditions` | Conditional | Production condition: name severity owner, communication owner, approval path, and minimum test slice |

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
| Open blockers | No active P0 stage failures after clean full P0 run. Bank Reco matched-environment mutation/integrity is closed. Remaining blockers/conditions are Payroll subscription entitlement plus remote-safe seed setup if Payroll is in scope, production security settings, SMTP/invite inbox proof, named support owner, support-observed error capture, audit captures, rollback, and hotfix readiness. |
| Accepted release conditions | Track 7 is `Passed With Conditions`: stage health, backup/readability, audit/error visibility, and operational contracts are proven; production security settings, named support owner, support-observed error capture, audit-view screenshots/exports, SMTP/invite inbox proof, and rollback/hotfix walkthrough must be completed before final go. |
| Deferred scope |  |
| Rollback readiness | Runbook checklist exists; stage backup/readability and artifact-size capture completed on 2026-09-03; final go requires release-lead/infra walkthrough and retention/restore acceptance. |
| Support coverage | SOPs and diagnostics path exist; final go requires named first-window support owner and ticket/channel confirmation. |
| Final decision |  |
