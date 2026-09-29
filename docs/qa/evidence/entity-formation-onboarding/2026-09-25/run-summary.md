# Entity Formation Onboarding Verification Run Summary

Date: 2026-09-25
Tester: Codex browser automation
Build/commit: Local workspace, uncommitted changes
Backend URL: Mocked browser API routes for Phase 0, Phase 1, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, and Phase 8; real local Django backend `http://127.0.0.1:8000` for Phase 2, Phase 9, Phase 10, Phase 11, Phase 11B, Phase 11C, Phase 11D, Phase 11E, Phase 11F, Phase 11G, Phase 11H, Phase 11I, Phase 11J, Phase 11K, Phase 11L, Phase 11M, Phase 11N, Phase 11O, Phase 11P, Phase 11Q, Phase 11R, Phase 11S, and Phase 11T live evidence
Frontend URL: Playwright managed Angular dev server, `http://127.0.0.1:4301`; local Angular server `http://localhost:4200` for Phase 9, Phase 10, Phase 11, Phase 11B, Phase 11C, Phase 11D, Phase 11E, Phase 11F, and Phase 11G; local Angular server `http://127.0.0.1:4302` for Phase 11H; local Angular server `http://127.0.0.1:4303` for Phase 11I; local Angular server `http://127.0.0.1:4304` for Phase 11J; local Angular server `http://127.0.0.1:4305` for Phase 11K; local Angular server `http://127.0.0.1:4306` for Phase 11L; local Angular server `http://127.0.0.1:4307` for Phase 11M; local Angular server `http://127.0.0.1:4308` for Phase 11N; local Angular server `http://127.0.0.1:4309` for Phase 11O; local Angular server `http://127.0.0.1:4310` for Phase 11P; local Angular server `http://127.0.0.1:4311` for Phase 11Q; local Angular server `http://127.0.0.1:4312` for Phase 11R; local Angular server `http://127.0.0.1:4313` for Phase 11S; local Angular server `http://127.0.0.1:4314` for Phase 11T
Browser(s): Chromium via Playwright

## Scope

Formation(s) tested: Partnership Phase 0 screen and route evidence; Phase 1 mocked formation matrix; Phase 2 live local backend formation matrix for proprietorship, partnership, LLP, company, OPC, Section 8, HUF, trust, society, NGO, cooperative, government entity, PSU, and unconfigured; Phase 3 browser CRUD workflow for signup, partner details, and organization structure; Phase 4 browser readiness workflow for business settings, branch workspace, static account bank mapping, and treasury cheque-book setup; Phase 5 capital distribution lifecycle for supported partnership and unsupported company; Phase 6 governed tax policy and tax working lifecycle for posted partnership appropriation; Phase 7 RBAC, route denial, view-only locking, and cross-entity isolation; Phase 8 desktop/mobile UX certification across onboarding and setup screens; Phase 9 live-local smoke on `EFO Live Company`; Phase 10 live CRUD certification on `EFO Live Partnership`; Phase 11 live Organization Structure CRUD sweep on `EFO Live Partnership`; Phase 11B live Employee and Employment Contract CRUD sweep on `EFO Live Partnership`; Phase 11C live Shift and Holiday Calendar CRUD sweep on `EFO Live Partnership`; Phase 11D HRMS onboarding adoption; Phase 11E leave runtime; Phase 11F attendance runtime; Phase 11G payroll run creation, calculation, employee trace, and mobile detail; Phase 11H payroll approval, posting, payment handoff/reconciliation, payment batches, reports, and ESS payslip; Phase 11I payroll reversal, payment batch approval block, duplicate-create block, cancellation, failed payment, and paid recovery; Phase 11J payroll report export, payment-batch export audit, ESS payslip PDF download, and restricted-permission action locking; Phase 11K payroll admin setup, period editor normalization, component CRUD, processing policy/rule CRUD, statutory scheme/registration CRUD, salary structure versioning, runtime readiness preview, and restricted setup mutation locking; Phase 11L statutory setup duplicate-validation feedback, inactive recovery, and mobile review; Phase 11M contract payroll profile creation, salary assignment, contract statutory profile binding, recurring/one-time pay items, and runtime readiness recheck; Phase 11N payroll setup edit/recovery, readiness refresh, and restricted setup mutation locking; Phase 11O payroll setup archive/recovery, duplicate and overlap safeguards, one-time status visibility, and branch-scope isolation; Phase 11P HRMS setup audit visibility and destructive-action confidence; Phase 11Q HRMS mobile table density, audit-column reachability, and delete-dialog reachability; Phase 11R keyboard activation and serious/critical axe accessibility checks; Phase 11S cross-browser Chromium/Firefox/WebKit confidence; Phase 11T performance/responsiveness guardrails across CFO Payables, CFO Receivables, CFO Cash Flow, Payroll Runs, and Organization Units on `EFO Live Partnership`
User/role: Superadmin-style browser session with onboarding, HRMS, settings, and capital distribution permissions; view-only RBAC browser session for Phase 7; live QA user `entity-formation-qa@example.com`
Entity/entities: Browser Partnership, entity id 58; live entities named `EFO Live <Formation>`; Phase 9 selected `EFO Live Company` entity id 189, financial year id 177; Phase 10, Phase 11, Phase 11B, Phase 11C, Phase 11D, Phase 11E, Phase 11F, Phase 11G, Phase 11H, Phase 11I, Phase 11J, Phase 11K, Phase 11L, Phase 11M, Phase 11N, Phase 11O, Phase 11P, Phase 11Q, Phase 11R, Phase 11S, and Phase 11T selected `EFO Live Partnership` entity id 187, financial year id 175
Financial year(s): FY 2026-27

## Result

Overall status: Phase 0, Phase 1, Phase 2 live local-backend, Phase 3 CRUD, Phase 4 business-readiness, Phase 5 capital-distribution, Phase 6 tax-working, Phase 7 RBAC/isolation, Phase 8 UX certification, Phase 9 live-local smoke, Phase 10 live CRUD certification, Phase 11 live setup CRUD sweep, Phase 11B employee/contract CRUD sweep, Phase 11C shift/calendar CRUD sweep, Phase 11D onboarding adoption, Phase 11E leave runtime, Phase 11F attendance runtime, Phase 11G payroll run runtime, Phase 11H payroll close runtime, Phase 11I payroll correction runtime, Phase 11J payroll export/audit/permission runtime, Phase 11K payroll admin setup, Phase 11L statutory setup negative-path browser evidence, Phase 11M payroll setup assignment/readiness evidence, Phase 11N payroll setup edit/recovery/permission evidence, Phase 11O payroll setup archive/duplicate/scope evidence, Phase 11P HRMS setup audit/delete-confidence evidence, Phase 11Q HRMS mobile table-density evidence, Phase 11R keyboard/accessibility evidence, Phase 11S cross-browser evidence, and Phase 11T performance/responsiveness evidence passed. Findings EFO-006 through EFO-042 are fixed or documented with the stated follow-up.

| Workflow | Status | Evidence |
|---|---|---|
| Public onboarding | Passed | screenshots/phase3-signup-*-desktop.png |
| Dashboard entity workspace | Not started | screenshots/ |
| Entity & Partner Details | Passed after visual fixes | screenshots/phase0-partnership-entity-partner-details-ownership-desktop.png, screenshots/phase0-partnership-entity-partner-details-add-row-desktop.png, screenshots/phase1-*-entity-partner-details-desktop.png, screenshots/phase2-live-*-entity-partner-details-desktop.png, screenshots/phase3-entity-partner-*-desktop.png, screenshots/phase8-ux-entity-partner-details-*.png |
| Organization Structure | Passed live full CRUD and UX certification | screenshots/phase0-organization-structure-list-desktop.png, screenshots/phase0-organization-structure-create-desktop.png, screenshots/phase3-org-structure-*-desktop.png, screenshots/phase8-ux-organization-units-desktop.png, screenshots/phase11-live-org-unit-*.png |
| Employees | Passed live full CRUD | screenshots/phase11b-live-employee-*.png |
| Employment Contracts | Passed live full CRUD and payroll eligibility toggle | screenshots/phase11b-live-contract-*.png |
| Shifts | Passed live full CRUD | screenshots/phase11c-live-shift-*.png |
| Holiday Calendars | Passed live full CRUD with holiday row create/update | screenshots/phase11c-live-calendar-*.png |
| Business Settings | Passed with settings save and UX certification | screenshots/phase0-business-settings-desktop.png, screenshots/phase4-business-settings-financial-*-desktop.png, screenshots/phase8-ux-business-settings-*.png |
| Branch workspace | Passed UX certification | screenshots/phase4-branch-*-desktop.png, screenshots/phase8-ux-branch-workspace-desktop.png |
| Bank accounts | Passed through static/treasury mapping | screenshots/phase4-static-account-bank-mapping-*-desktop.png, screenshots/phase4-treasury-setup-*-desktop.png |
| Static Account Settings | Passed bank mapping save and UX certification | screenshots/phase4-static-account-bank-mapping-*-desktop.png, screenshots/phase8-ux-static-account-settings-desktop.png |
| Capital & Distribution | Passed full supported lifecycle, unsupported company block, and UX certification | screenshots/phase0-capital-distribution-ready-desktop.png, screenshots/phase1-*-capital-distribution-desktop.png, screenshots/phase2-live-*-capital-distribution-desktop.png, screenshots/phase5-capital-*-desktop.png, screenshots/phase8-ux-capital-distribution-*.png |
| Tax Policy / Tax Working | Passed governed lifecycle | screenshots/phase6-tax-policy-*-desktop.png, screenshots/phase6-tax-working-*-desktop.png |
| RBAC / isolation | Passed | screenshots/phase7-rbac-*-desktop.png |
| Mobile layout | Passed after fix and Phase 8 certification | screenshots/phase0-partnership-entity-partner-details-ownership-mobile.png, screenshots/phase8-ux-*-mobile.png |
| UX certification | Passed | screenshots/phase8-ux-*.png |
| Phase 9 live-local smoke | Passed after fixes | screenshots/phase9-live-*.png |
| Phase 10 live CRUD certification | Passed after fixes | screenshots/phase10-live-*.png |
| Phase 11 live setup CRUD sweep | Passed after fix | screenshots/phase11-live-org-unit-*.png |
| Phase 11B live employee/contract CRUD sweep | Passed after fixes | screenshots/phase11b-live-*.png |
| Phase 11C live shift/calendar CRUD sweep | Passed after fixes | screenshots/phase11c-live-*.png |
| Phase 11G live payroll run runtime | Passed after UX fix | screenshots/phase11g-live-*.png |
| Phase 11H live payroll close runtime | Passed after fixes | screenshots/phase11h-live-*.png |
| Phase 11I live payroll correction runtime | Passed after fix | screenshots/phase11i-live-*.png |
| Phase 11J live payroll export/audit/permission runtime | Passed after UX fix | screenshots/phase11j-live-*.png |
| Phase 11K live payroll admin setup | Passed after fixes | screenshots/phase11k-live-*.png |
| Phase 11L live statutory setup negative paths | Passed after UX fix | screenshots/phase11l-live-statutory-*.png, screenshots/phase11l-live-payroll-setup-negative-paths-mobile.png |
| Phase 11M live payroll setup assignment/readiness | Passed after UX fixes | screenshots/phase11m-live-*.png |
| Phase 11N live payroll setup edit/recovery/permissions | Passed after fixes | screenshots/phase11n-live-*.png |
| Phase 11O live payroll setup archive/duplicates/scope | Passed after fixes | screenshots/phase11o-live-*.png |
| Phase 11P live HRMS setup audit/delete confidence | Passed after UX fixes | screenshots/phase11p-live-*.png |
| Phase 11Q live HRMS mobile table density | Passed | screenshots/phase11q-live-*.png |
| Phase 11R live accessibility and keyboard confidence | Passed after UX fixes | screenshots/phase11r-live-*.png |
| Phase 11S live cross-browser confidence | Passed | screenshots/phase11s-live-*.png |
| Phase 11T live performance and responsiveness | Passed | screenshots/phase11t-live-*.png |

## Formation Matrix

| Formation | Entity & Partner Details | Capital Distribution Readiness | Evidence |
|---|---|---|---|
| Proprietorship | Passed | Passed as Wave 1 supported | screenshots/phase1-proprietorship-entity-partner-details-desktop.png, screenshots/phase1-proprietorship-capital-distribution-desktop.png |
| Partnership | Passed | Passed as Wave 1 supported | screenshots/phase1-partnership-entity-partner-details-desktop.png, screenshots/phase1-partnership-capital-distribution-desktop.png |
| LLP | Passed | Passed as Wave 1 supported | screenshots/phase1-llp-entity-partner-details-desktop.png, screenshots/phase1-llp-capital-distribution-desktop.png |
| Company | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-company-entity-partner-details-desktop.png, screenshots/phase1-company-capital-distribution-desktop.png |
| OPC | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-opc-entity-partner-details-desktop.png, screenshots/phase1-opc-capital-distribution-desktop.png |
| Section 8 | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-section-8-entity-partner-details-desktop.png, screenshots/phase1-section-8-capital-distribution-desktop.png |
| HUF | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-huf-entity-partner-details-desktop.png, screenshots/phase1-huf-capital-distribution-desktop.png |
| Trust | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-trust-entity-partner-details-desktop.png, screenshots/phase1-trust-capital-distribution-desktop.png |
| Society | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-society-entity-partner-details-desktop.png, screenshots/phase1-society-capital-distribution-desktop.png |
| NGO | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-ngo-entity-partner-details-desktop.png, screenshots/phase1-ngo-capital-distribution-desktop.png |
| Cooperative | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-cooperative-entity-partner-details-desktop.png, screenshots/phase1-cooperative-capital-distribution-desktop.png |
| Government Entity | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-government-entity-entity-partner-details-desktop.png, screenshots/phase1-government-entity-capital-distribution-desktop.png |
| PSU | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase1-psu-entity-partner-details-desktop.png, screenshots/phase1-psu-capital-distribution-desktop.png |
| Unconfigured | Passed blank/setup-required state | Passed formation-not-configured blocker | screenshots/phase1-unconfigured-entity-partner-details-desktop.png, screenshots/phase1-unconfigured-capital-distribution-desktop.png |

## Phase 2 Live Local Backend Matrix

Each row was created or reused through the real onboarding API, loaded in Chromium through Angular, and screenshot on both Entity & Partner Details and Capital & Distribution.

| Formation | Live Onboarding API | Entity & Partner Details | Capital Distribution Readiness | Evidence |
|---|---|---|---|---|
| Proprietorship | Passed | Passed | Passed as Wave 1 supported | screenshots/phase2-live-proprietorship-entity-partner-details-desktop.png, screenshots/phase2-live-proprietorship-capital-distribution-desktop.png |
| Partnership | Passed | Passed | Passed as Wave 1 supported | screenshots/phase2-live-partnership-entity-partner-details-desktop.png, screenshots/phase2-live-partnership-capital-distribution-desktop.png |
| LLP | Passed | Passed | Passed as Wave 1 supported | screenshots/phase2-live-llp-entity-partner-details-desktop.png, screenshots/phase2-live-llp-capital-distribution-desktop.png |
| Company | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-company-entity-partner-details-desktop.png, screenshots/phase2-live-company-capital-distribution-desktop.png |
| OPC | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-opc-entity-partner-details-desktop.png, screenshots/phase2-live-opc-capital-distribution-desktop.png |
| Section 8 | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-section-8-entity-partner-details-desktop.png, screenshots/phase2-live-section-8-capital-distribution-desktop.png |
| HUF | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-huf-entity-partner-details-desktop.png, screenshots/phase2-live-huf-capital-distribution-desktop.png |
| Trust | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-trust-entity-partner-details-desktop.png, screenshots/phase2-live-trust-capital-distribution-desktop.png |
| Society | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-society-entity-partner-details-desktop.png, screenshots/phase2-live-society-capital-distribution-desktop.png |
| NGO | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-ngo-entity-partner-details-desktop.png, screenshots/phase2-live-ngo-capital-distribution-desktop.png |
| Cooperative | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-cooperative-entity-partner-details-desktop.png, screenshots/phase2-live-cooperative-capital-distribution-desktop.png |
| Government Entity | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-government-entity-partner-details-desktop.png, screenshots/phase2-live-government-capital-distribution-desktop.png |
| PSU | Passed | Passed | Passed as unsupported/blocked for Wave 1 | screenshots/phase2-live-psu-entity-partner-details-desktop.png, screenshots/phase2-live-psu-capital-distribution-desktop.png |
| Unconfigured | Passed | Passed blank/setup-required state | Passed formation-not-configured blocker | screenshots/phase2-live-unconfigured-entity-partner-details-desktop.png, screenshots/phase2-live-unconfigured-capital-distribution-desktop.png |

## UX Review

| Page | Desktop | Mobile | Notes |
|---|---|---|---|
| Public Signup | Passed | Not reviewed | Browser flow reaches final review and submits trial signup payload from the review step only. |
| Entity & Partner Details | Passed | Passed | Ownership section opens directly from `/entity-partner-details`; Add Row creates another ownership row; mobile header no longer overlaps; Phase 8 rechecked desktop/mobile button clipping and shell alignment. |
| Organization Structure | Passed | Passed | Create, edit, deactivate, include inactive, confirm delete, and post-delete list state work through `/hrms/organization-units`; Phase 8 rechecked desktop alignment; Phase 11P verifies Last Updated audit visibility and soft-delete warning copy; Phase 11Q verifies mobile table scrolling, Last Updated reachability, and delete dialog access. |
| HRMS Onboarding | Passed | Passed | Template preview, recommended adoption, repeat adoption idempotence, adopted setup rename, restore, and mobile layout work through `/hrms/onboarding`. |
| Leave Policy Setup | Passed | Not reviewed | Adopted leave policies load with named controls; advanced rule edit/save/restore works through `/hrms/leave-policy-rules`. |
| Leave Balance Ledger | Passed | Passed | Temporary employee/contract setup, policy entitlement bootstrap, opening ledger evidence, mobile layout, and cleanup work through browser UI. |
| Daily Attendance Grid | Passed | Not reviewed | Payroll period prerequisite, contract-scoped grid load, month save, persisted reload, and screenshots work through `/hrms/attendance-daily-grid`; manual mixed draft edits need follow-up hardening. |
| Attendance Import | Passed | Not reviewed | CSV validate, commit, processed batch visibility, and shared-contract branch context work through `/hrms/attendance-import`. |
| Monthly Attendance Summary | Passed | Passed | Imported attendance appears in monthly summary, with desktop and mobile screenshots captured through `/hrms/attendance-monthly-summary`. |
| Payroll Runs | Passed after UX fix | Passed | Create panel loads, period selection auto-fills posting and payout dates, run creation returns preflight evidence, and list refreshes through `/payroll/runs`; Phase 11R verifies keyboard activation of Create Run and programmatic labels on create/filter controls. |
| Payroll Periods | Passed after fix | Not reviewed | Phase 11K verifies period edit opens with backend dates normalized into browser date inputs so users can review and save without blank required dates. |
| Payroll Components | Passed after UX fix | Not reviewed | Phase 11K verifies component create/update through `/payroll/components`; semantic code is now a guided dropdown using backend-supported choices. |
| Payroll Policies / Rules | Passed after fix | Not reviewed | Phase 11K verifies processing policy creation, rule-builder save, and view-only mutation locks through `/payroll/policies`. |
| Payroll Statutory Setup | Passed after UX fix | Passed | Phase 11K verifies statutory scheme and registration create flows plus restricted-session disabled states; Phase 11L verifies duplicate scheme/registration feedback, inactive recovery, and mobile review through `/payroll/statutory/schemes` and `/payroll/statutory/registrations`. |
| Payroll Salary Structures | Passed | Not reviewed | Phase 11K verifies salary structure creation, component line entry, edit, and versioned update through `/payroll/salary-structures`. |
| Payroll Contract Profiles / Salary Assignments | Passed after UX fix | Passed | Phase 11M verifies new contract payroll profile creation from `PW-E2E-CONTRACT-NEW`, local date validation beside fields, and salary structure assignment creation through `/payroll/contract-profiles`; Phase 11N verifies contract profile edit, salary assignment edit, disabled view-only mutations, and mobile layout evidence; Phase 11O verifies duplicate active-profile field feedback, salary assignment overlap field feedback, close-previous rollover, archive/recovery, and branch-scope isolation. |
| Payroll Contract Statutory Profiles | Passed after UX fix | Not reviewed | Phase 11M verifies contract-level statutory applicability creation, local effective-date field feedback, filtering, and row visibility through `/payroll/statutory/contract-profiles`; Phase 11N verifies inactive recovery and view-only mutation locking. |
| Payroll Recurring / One-Time Pay Items | Passed after UX fix | Not reviewed | Phase 11M verifies recurring pay item and one-time item create flows, local amount/date validation beside fields, payroll period selection, and row reload evidence through `/payroll/recurring-pay-items` and `/payroll/one-time-pay-items`; Phase 11N verifies inactive recovery and view-only mutation locking; Phase 11O adds visible Active/Inactive status to one-time pay item rows so archive filters are understandable. |
| Payroll Runtime Readiness | Passed | Passed | Phase 11K verifies readiness preview summary and mobile layout through `/payroll/runtime/readiness`; Phase 11M verifies readiness reflects newly assigned salary setup and recurring/one-time item counts for the new contract; Phase 11N verifies readiness remains clean after setup edits and recovery. |
| Payroll Run Detail | Passed | Passed | Created run opens, workflow readiness renders, calculate action completes through confirmation dialog, and mobile detail layout remains readable through `/payroll/runs/:id`. |
| Employee Payroll Trace | Passed | Not reviewed | Calculated employee grid renders and the employee trace drawer opens with component breakdown evidence. |
| Payroll Approval / Posting | Passed | Passed | Submit, approve, post, payment handoff, and payment reconciliation complete through confirmation dialogs on `/payroll/runs/:id`; run-detail navigation now reloads when the route id changes. |
| Payroll Payment Batches | Passed | Not reviewed | Batch list, approved batch detail, export, and mark-paid actions complete through `/payroll/payment-batches` and `/payroll/payment-batches/:id`. |
| Payroll Correction / Payment Exceptions | Passed | Passed | Reversal requires reason and acknowledgement, invalid batches block approval, duplicate active batch creation shows inline error, validated batches cancel, exported batches can be marked failed and then recovered to paid. |
| Payroll Reports | Passed | Not reviewed | Payroll register loads for period `SEP-2026-PW-E2E` with status `POSTED`; Phase 11J verifies report export download and restricted-session export locking through `/payroll/reports`. |
| Payroll Export / Audit Trail | Passed | Passed | Phase 11J verifies payroll register export, payment-batch export history, export reference evidence, payment-batch CSV re-download, and mobile audit layout. |
| Payroll Permissions | Passed | Not reviewed | Phase 11J verifies restricted payroll sessions can view payroll reports/runs while export, reverse, handoff, and payment batch mutation actions remain disabled; Phase 11K extends this to period, component, policy, statutory, and salary-structure setup mutations. |
| ESS Payslips | Passed after UX fixes | Passed | Employee self-service payslip list/detail show the seeded payslip, PDF downloads complete through browser, both pages expose durable in-page download feedback, and Phase 11R verifies programmatic labels on the ESS filters. |
| Employees | Passed | Passed | Create, reload, edit, compliance update, deactivate, reactivate, confirm delete, and post-delete list state work through `/hrms/employees`; Phase 11P verifies Last Updated audit visibility and soft-delete warning copy; Phase 11Q verifies mobile table scrolling, Last Updated reachability, and delete dialog access. |
| Employment Contracts | Passed | Passed | Employee lookup, contract create, reload, edit, assignment/schedule tabs, payroll eligibility disable/enable, confirm delete, and post-delete list state work through `/hrms/contracts`; Phase 11P verifies Last Updated audit visibility and contract-specific soft-delete warning copy; Phase 11Q verifies mobile table scrolling, Last Updated reachability, and delete dialog access. |
| Shifts | Passed | Passed | Create with timing rules, reload, edit, deactivate, reactivate, confirm delete, and post-delete list state work through `/hrms/shifts`; Phase 11P verifies Last Updated audit visibility and soft-delete warning copy; Phase 11Q verifies mobile table scrolling, Last Updated reachability, and delete dialog access. |
| Holiday Calendars | Passed | Passed | Calendar create with holiday row, reload, edit calendar/holiday row, deactivate, reactivate, confirm delete, and post-delete list state work through `/hrms/holiday-calendars`; Phase 11P verifies Last Updated audit visibility and soft-delete warning copy; Phase 11Q verifies mobile table scrolling, Last Updated reachability, and delete dialog access. |
| Business Settings | Passed | Passed | Financial settings module renders through `/businesssettings`; branch-scope toggle edits and module save complete through browser; Phase 8 rechecked desktop/mobile layout. |
| Branch Workspace | Passed | Not reviewed | Directory search, summary cards, branch table, and unified entity branch editor open correctly through `/branch`; Phase 8 rechecked desktop layout. |
| Static Account Settings | Passed | Not reviewed | Missing bank mapping validation is visible; browser maps ICICI bank to a ledger and validation clears; Phase 8 rechecked desktop layout. |
| Treasury Setup | Passed | Not reviewed | Explicit bank mapping readiness is visible; cheque book creation works through browser form. |
| Capital & Distribution | Passed | Passed | Partnership migration, policy approval, stakeholder mapping, activation, calculation, submit/approve/post/reverse, statement, and health views complete through browser; company unsupported state blocks Wave 1 policy creation; Phase 8 rechecked desktop/mobile layout. |
| Tax Policy / Tax Working | Passed | Not reviewed | Tax policy create, submit, approve, posted-run tax working calculate, evidence-backed override, reproduction check, submit, approve, and reverse complete through browser. |
| RBAC / isolation | Passed | Not reviewed | View-only menu evidence, hidden branch manage action, disabled static/capital mutation actions, unauthorized direct-route screen, and cross-entity 403 message verified through browser. |

## Defects

| ID | Severity | Screen | Issue | Screenshot | Status |
|---|---|---|---|---|---|
| EFO-001 | High | Entity & Partner Details mobile | Header summary card overlapped the title/content because the internal-mode header grid kept two columns under 991px. | Initial failing Playwright screenshot in `accountproject/test-results/.../test-failed-1.png` | Fixed in `entity-master-form.component.scss`; retested with `phase0-partnership-entity-partner-details-ownership-mobile.png`. |
| EFO-002 | Low | Entity & Partner Details mobile | Tab intro pill could clip text on narrow content width. | `phase0-partnership-entity-partner-details-ownership-mobile.png` | Fixed with mobile wrapping for `.tab-intro-pill`; retested. |
| EFO-003 | Medium | Shell / Entity & Partner Details | Hover-expanded sidebar could cover routed content because shell layout offsets were not reapplied when hover state changed. | Initial `phase2-live-partnership-entity-partner-details-desktop.png` during live visual review | Fixed in `route.component.ts`; live evidence test now asserts routed content starts after the sidebar before screenshots. |
| EFO-004 | Medium | Entity & Partner Details / Capital & Distribution | Desktop tab strips could clip the last tab on wide-but-constrained content. | Initial live screenshots for partnership entity editor and unconfigured capital distribution | Fixed tab wrapping/fitting in `entity-master-form.component.scss` and `capital-distribution-setup.component.scss`; retested with refreshed Phase 2 screenshots. |
| EFO-005 | Test data | Entity & Partner Details | Browser CRUD save was blocked when test data used invalid GSTIN/state-code combinations. | Phase 3 failed-run screenshots under `accountproject/test-results/...` | Corrected Phase 3 mocked entity to use unregistered/no-GST because partner CRUD is the test scope. |
| EFO-006 | High | Business Settings live local | Real backend returned 500 for `GET /api/financial/settings-hub/?entity=189&entityfinid=177` because Settings Hub created first-run Sales settings without passing the financial year id required by `SalesSettingsService`. | screenshots/phase9-live-business-settings-desktop.png | Fixed in `financial/views_settings_hub.py`; retested with Phase 9 live-local smoke and refreshed screenshot shows Business Settings loaded. |
| EFO-007 | Medium | Branch Workspace live local | Live QA role for `EFO Live Company` was denied direct access to `/branch`; the menu and `admin.branch.*` grants were missing/inactive in the superadmin setup path. | screenshots/phase9-live-branch-workspace-desktop.png | Fixed in `rbac/access_catalog.py`, `rbac/migrations/0195_add_branch_workspace_superadmin_menu.py`, and `rbac/migrations/0196_activate_branch_workspace_crud_permissions.py`; retested with Phase 9 live-local smoke and refreshed screenshot shows Branch Workspace loaded. |
| EFO-008 | Medium | Entity & Partner Details / Branch editor | Required contract validation surfaced as generic `Review: Required by onboarding meta`, so users could not tell that entity phone was missing. | Phase 10 failed-run screenshot under `accountproject/test-results/...` | Fixed in `entity-master-form.component.html`, `.scss`, and `.ts`; validation cards now show field label plus message and route `entity.phoneoffice` to Contact. |
| EFO-009 | High | Business Settings | Settings Hub API returned `schema` as arrays and `scope` as an object; the Angular page treated both as strings/records, causing render errors and hiding all editable fields. | Phase 10 failed-run screenshot under `accountproject/test-results/...` | Fixed in `setting.component.ts`; schema arrays normalize by `name`, and scope chips handle entity/branch scope objects. Retested with Phase 10 settings toggle/save/reload. |
| EFO-010 | High | Organization Structure | Superadmin live QA role only had `hrms.organization_unit.view`, hiding create/update/delete actions and preventing end-to-end onboarding setup. | Phase 10 failed-run screenshot under `accountproject/test-results/...` | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0197_activate_org_unit_crud_superadmin.py`; migration applied locally and Phase 10 org-unit create/reload passed. |
| EFO-011 | High | Organization Structure | `Show inactive` included soft-deleted organization units because the list service started from `all_objects`; after delete, the row could still appear in the setup list. | Phase 11 failed-run screenshot under `accountproject/test-results/...` | Fixed in `hrms/services/organization.py`; added regression coverage in `hrms/tests/test_services.py`; Phase 11 full CRUD sweep passed. |
| EFO-012 | High | Employees / Employment Contracts | Superadmin live QA role had HRMS employee/contract view permissions but not create/update/delete, blocking downstream onboarding setup. | Phase 11B preflight permission assertion | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0198_activate_employee_contract_crud_superadmin.py`; migration applied locally and Phase 11B browser CRUD passed. |
| EFO-013 | High | Employees / Employment Contracts | `Show inactive` could include soft-deleted employees and contracts because the list services started from `all_objects`. | Backend regression coverage | Fixed in `hrms/services/employees.py` and `hrms/services/contracts.py`; added regression coverage in `hrms/tests/test_services.py`; Phase 11B browser CRUD passed. |
| EFO-014 | High | Shifts / Holiday Calendars | Superadmin live QA role had HRMS shift/calendar view permissions but not create/update/delete, blocking schedule/calendar setup. | Phase 11C preflight permission assertion | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0199_activate_shift_calendar_crud_superadmin.py`; migration applied locally and Phase 11C browser CRUD passed. |
| EFO-015 | High | Shifts / Holiday Calendars | `Show inactive` could include soft-deleted shifts and holiday calendars because the list services started from `all_objects`. | Backend regression coverage | Fixed in `hrms/services/shifts.py` and `hrms/services/holidays.py`; added regression coverage in `hrms/tests/test_services.py`; Phase 11C browser CRUD passed. |
| EFO-016 | Medium | Holiday Calendars | Calendar payload serialized all related holiday rows, including soft-deleted holiday rows. | Code review during Phase 11C backend hardening | Fixed in `HrHolidayCalendarSerializer` to serialize only `deleted_at IS NULL` holiday rows; Phase 11C create/edit/reload evidence passed. |
| EFO-017 | High | HRMS Onboarding | Superadmin live QA role had onboarding view but not adopt/update, blocking one-click setup adoption and adopted setup refinement. | Phase 11D preflight permission assertion | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0200_activate_hrms_onboarding_superadmin.py`; migration applied locally and Phase 11D browser adoption/rename passed. |
| EFO-018 | High | HRMS Onboarding | Pressing Adopt Recommended repeatedly created duplicate setup rows or could fail on same-year holiday calendar uniqueness. | Backend regression coverage and Phase 11D repeat-adopt browser step | Fixed in `hrms/services/hrms_global_adoption_service.py`; adoption now reuses existing records for the same entity/scope/source/year. |
| EFO-019 | High | Leave Policy / Leave Ledger | Superadmin live QA role had leave policy and ledger view permissions but not leave-policy update or leave-balance view, blocking rule saves and entitlement bootstrap. | Phase 11E preflight permission assertion | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0201_activate_hrms_leave_runtime_superadmin.py`; migration applied locally and Phase 11E browser leave runtime passed. |
| EFO-020 | High | Attendance Runtime | Superadmin live QA role had attendance runtime view permissions but not daily-entry create/update or import-batch create, blocking attendance save/import workflows. | Phase 11F preflight permission assertion | Fixed in `rbac/access_catalog.py` and `rbac/migrations/0202_activate_hrms_attendance_runtime_superadmin.py`; migration applied locally and Phase 11F browser attendance runtime passed. |
| EFO-021 | High | Attendance Runtime | Branch-scoped attendance screens listed shared/root employment contracts but bulk save/import rejected them as invalid or mismatched against branch import batches. | Phase 11F failed browser runs | Fixed in `hrms/views.py` and `hrms/services/attendance_capture_service.py`; shared contracts are accepted in branch context and CSV batches become shared when rows target shared contracts. Phase 11F browser runtime passed. |
| EFO-022 | Medium | Daily Attendance Grid | Manual mixed draft edits in the grid can be lost before save because the rendered control state and row model can diverge during Angular change detection. | Phase 11F failed browser runs | Partially hardened in `attendance-daily-grid.component.html` and `.ts`; current certified path covers grid load/save and uses CSV import for attendance mutation. Follow-up: convert grid to reactive `FormArray` before marking manual mixed edits 9/10. |
| EFO-023 | High | Payroll Runs | Create Payroll Run submitted `posting_date: null` even though posting date is required by the backend, creating a hidden validation failure for users. | Phase 11G failed browser run under `accountproject/test-results/...` | Fixed in `payroll/pages/runs/runs.component.ts` and `.html`; selecting a payroll period now auto-fills posting/payout dates and the form shows a clear posting-date validation message if needed. Phase 11G browser runtime passed. |
| EFO-024 | High | Payroll Run Detail | Navigating from one payroll run detail to another reused the Angular component without reloading data, so users could see stale status/actions for the previous run. | Phase 11H failed browser run under `accountproject/test-results/...` | Fixed in `payroll/pages/run-detail/run-detail.component.ts`; route param changes now reload the run and clear stale action banners/confirmations. Phase 11H browser runtime passed. |
| EFO-025 | High | Payroll Run Detail | Approved runs showed the Post action as disabled because the expected pre-post `MISSING_POSTED_ENTRY_ID` verification issue was treated as a blocker, and the API mapper stripped issue codes needed by workflow logic. | Phase 11H failed browser run under `accountproject/test-results/...` | Fixed in `payroll/utils/payroll-workflow.ts`, `payroll/models/payroll.models.ts`, and `payroll/services/payroll-api.service.ts`; approved runs can post while true blocking issues still block action. Phase 11H browser runtime passed. |
| EFO-026 | High | Payment Batch Detail | Navigating from one payment batch detail to another reused the Angular component without reloading data, leaving stale batch status, actions, and form values on screen. | Phase 11I failed browser run under `accountproject/test-results/...` | Fixed in `payroll/pages/payment-batch-detail/payment-batch-detail.component.ts`; route param changes now reload the batch and clear stale action fields. Phase 11I browser runtime passed. |
| EFO-027 | Medium | ESS Payslip Downloads | Payslip PDF downloads depended on transient toast feedback only, leaving no durable in-page confirmation for employees after the browser-triggered file download. | Phase 11J failed browser run under `accountproject/test-results/...` | Fixed in `payroll/pages/ess-payslips` and `payroll/pages/ess-payslip-detail`; both list and detail pages now show an inline `role=status` confirmation after PDF generation/download. Phase 11J browser runtime passed. |
| EFO-028 | High | Payroll Periods | Period edit forms could receive backend `DD-MM-YYYY` dates, leaving HTML date inputs blank and turning a simple edit into a generic validation failure. | Phase 11K failed browser run under `accountproject/test-results/...` | Fixed in `payroll/services/payroll-api.service.ts`; period dates now normalize to `YYYY-MM-DD` for edit controls. Phase 11K browser setup evidence passed. |
| EFO-029 | Medium | Payroll Components | Semantic code was a free-text field even though the backend accepts a constrained choice list, so users could type invalid values and hit backend validation errors. | Phase 11K failed browser run under `accountproject/test-results/...` | Fixed in `payroll/components/payroll-component-form`; semantic code is now a select list with supported backend choices. Phase 11K component CRUD passed. |
| EFO-030 | High | Payroll Setup Permissions | Payroll policy and statutory setup screens exposed mutation buttons in restricted view-only sessions, creating confusing dead-end or unauthorized actions. | Phase 11K restricted-permission browser evidence | Fixed in `payroll/services/payroll-permission.service.ts`, `payroll/pages/policies`, `payroll/pages/statutory-schemes`, `payroll/pages/statutory-rules`, and `payroll/pages/statutory-registrations`; restricted browser checks now show setup mutation actions disabled. |
| EFO-031 | Medium | Payroll Statutory Setup | Composite uniqueness failures for statutory schemes and registrations surfaced as generic modal errors or form-level errors instead of appearing beside the user-editable code/registration fields. | Phase 11L browser negative-path review | Fixed in `payroll/pages/statutory-schemes`, `payroll/pages/statutory-registrations`, `payroll/pages/statutory-rules`, and shared statutory setup styling; model-level uniqueness errors now render beside the relevant field. Phase 11L browser evidence passed. |
| EFO-032 | Medium | Payroll Assignment / Pay Items | Contract profile, salary assignment, recurring pay item, and one-time pay item screens used generic modal banners for recoverable validation, making it harder for users to know which field to fix. | Phase 11M browser assignment/readiness review | Fixed in `payroll/pages/contract-profiles`, `payroll/pages/recurring-pay-items`, and `payroll/pages/one-time-pay-items`; local and backend validation now renders beside the relevant field while retaining the modal summary. Phase 11M browser evidence passed. |
| EFO-033 | Medium | Payroll Contract Statutory Profiles | Local effective-date and JSON validation on contract statutory profiles appeared only as a compact banner even after backend field-error support was added. | Phase 11M failed browser run at statutory profile validation | Fixed in `payroll/pages/statutory-contract-profiles`; local date and JSON validation now populates field-level errors for `effective_to`, `override_rule_json`, and `metadata`. Phase 11M browser evidence passed. |
| EFO-034 | High | Payroll Contract Profiles | Contract profile edit could send backend-formatted dates back into browser date fields, causing a wrong-format `payroll_start_date` validation failure on a simple profile update. | Phase 11N failed browser edit run | Fixed in `payroll/services/payroll-api.service.ts`; contract profile and HRMS contract dates now normalize to `YYYY-MM-DD` for edit controls and update payloads. Phase 11N browser evidence passed. |
| EFO-035 | High | Payroll Setup Permissions | Contract profile, salary assignment, contract statutory profile, recurring pay item, and one-time pay item screens did not consistently lock create/edit actions in restricted view-only sessions. | Phase 11N restricted-permission browser evidence | Fixed in `payroll/services/payroll-permission.service.ts` and the affected setup pages; view-only browser checks now show mutation buttons disabled and guarded. Phase 11N browser evidence passed. |
| EFO-036 | Medium | Payroll Contract Profiles / Salary Assignments | Duplicate active contract profile and overlapping salary assignment errors surfaced as generic modal messages instead of pointing users to the contract or effective-date field to fix. | Phase 11O browser duplicate/overlap review | Fixed in `payroll/views/payroll_setup_views.py`; service validation errors now map to field-level API errors for `hrms_contract`, `payroll_end_date`, `effective_from`, `effective_to`, `salary_structure`, and `salary_structure_version`. Phase 11O browser evidence passed. |
| EFO-037 | Medium | One-Time Pay Items | The one-time pay item list had active/inactive filtering but no visible status column, making archive/recovery review unclear for end users. | Phase 11O UX review | Fixed in `payroll/pages/one-time-pay-items/one-time-pay-items.component.html`; list rows now show an Active/Inactive status pill. Phase 11O browser evidence passed. |
| EFO-038 | High | Payroll Scope Safety | Payroll setup pages could default back to Head Office when no explicit override was supplied, allowing branch-scoped users to see Head Office payroll setup data. | Phase 11O branch-scope browser review | Fixed in `payroll/services/payroll-scope.service.ts`; scope snapshots now preserve the stored current subentity from `CommonService.getCurrentSubentityId()`. Phase 11O verifies an alternate branch has no Head Office contract profile leakage. |
| EFO-039 | Medium | HRMS Setup Audit Visibility | Organization Units, Employees, Employment Contracts, Shifts, and Holiday Calendars stored audit timestamps but did not expose a usable Last Updated cue in setup lists; date-pipe rendering also blanked backend `DD-MM-YYYY` dates. | Phase 11P browser audit review | Fixed in the affected HRMS setup list templates and sort unions; rows now display backend Last Updated values directly. Phase 11P browser evidence passed. |
| EFO-040 | Medium | HRMS Destructive Action Confidence | HRMS delete confirmations were terse and the shared confirm dialog could clip longer safety text, so users could not clearly distinguish temporary deactivate from soft delete retained for audit. | Phase 11P browser delete-dialog review | Fixed in `catalog-confirm-dialog.component.ts` and affected HRMS setup components; delete confirmations now explain soft-delete/audit retention and point users to deactivate or operational toggles for temporary control. Phase 11P browser evidence passed. |
| EFO-041 | Medium | Payroll Runs Accessibility | Payroll Runs create/filter inputs and selects used visible labels that were not programmatically connected, leaving several controls unnamed for assistive technology. | Phase 11R browser accessibility review | Fixed in `payroll/pages/runs/runs.component.html`; create-run and filter controls now expose explicit accessible labels. Phase 11R axe/keyboard evidence passed. |
| EFO-042 | Medium | ESS Payslips Accessibility | ESS Payslip period/status/payment filters had visual labels but the selects were reported as unnamed controls by axe. | Phase 11R browser accessibility review | Fixed in `payroll/pages/ess-payslips/ess-payslips.component.html`; ESS filters now expose explicit accessible labels. Phase 11R axe/keyboard evidence passed. |

## Retest Notes

- Browser command: `npx playwright test playwright/tests/entity-formation-browser-evidence.spec.ts --project=chromium --reporter=list`
- Result: 2 passed.
- Formation matrix browser command: `npx playwright test playwright/tests/entity-formation-matrix-browser-evidence.spec.ts --project=chromium --reporter=list`
- Result: 28 passed.
- Live local backend browser command: `EFO_LIVE_ENABLE=1 npx playwright test playwright/tests/entity-formation-live-browser-evidence.spec.ts --project=chromium --reporter=list`
- Result: 14 passed.
- Phase 3 CRUD browser command: `npx playwright test playwright/tests/entity-formation-phase3-workflow-crud.spec.ts --project=chromium --reporter=list`
- Result: 3 passed.
- Phase 4 business-readiness browser command: `npx playwright test playwright/tests/entity-formation-phase4-business-readiness.spec.ts --project=chromium --reporter=list`
- Result: 3 passed.
- Phase 5 capital-distribution browser command: `npx playwright test playwright/tests/entity-formation-phase5-capital-distribution.spec.ts --project=chromium --reporter=list`
- Result: 2 passed.
- Phase 6 tax-working browser command: `npx playwright test playwright/tests/entity-formation-phase6-tax-working.spec.ts --project=chromium --reporter=list`
- Result: 1 passed.
- Phase 7 RBAC/isolation browser command: `npx playwright test playwright/tests/entity-formation-phase7-rbac-isolation.spec.ts --project=chromium --reporter=list`
- Result: 4 passed.
- Phase 8 UX-certification browser command: `npx playwright test playwright/tests/entity-formation-phase8-ux-certification.spec.ts --project=chromium --reporter=list`
- Result: 2 passed.
- Phase 9 live-local smoke command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase9-live-local-smoke.spec.ts --project=chromium --reporter=list`
- Result: 2 passed; Business Settings and Branch Workspace loaded after EFO-006/EFO-007 fixes, CFO payables loaded and screenshot captured.
- Phase 10 live CRUD certification command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase10-live-crud-certification.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; ownership agreement edit persisted, branch created and reloaded, Business Settings PAN uniqueness toggle saved and reloaded, and Organization Unit created and reloaded through browser UI. Screenshots captured as `screenshots/phase10-live-*.png`.
- Phase 11 live setup CRUD sweep command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11-live-setup-crud-sweep.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; Organization Unit create, reload, edit, deactivate, include-inactive visibility, reactivate, delete confirmation, and post-delete empty-search state completed through browser UI. Screenshots captured as `screenshots/phase11-live-org-unit-*.png`.
- Backend regression command after EFO-011 fix: `venv/bin/python manage.py test hrms.tests.test_services.HrmsServiceTests.test_organization_unit_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_organization_unit_service_filters_status --keepdb`
- Result: 2 passed.
- Phase 11B live employee/contract CRUD command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11b-live-employee-contract-crud.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; employee create/reload/edit/deactivate/reactivate/delete and employment contract create/reload/edit/payroll-disable/payroll-enable/delete completed through browser UI. Screenshots captured as `screenshots/phase11b-live-*.png`.
- RBAC migration command after EFO-012 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0198 applied; employee and employment-contract view/create/update/delete permissions are active for superadmin/admin role family.
- Backend regression command after EFO-013 fix: `venv/bin/python manage.py test hrms.tests.test_services.HrmsServiceTests.test_employee_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_contract_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_organization_unit_service_excludes_deleted_when_including_inactive --keepdb`
- Result: 3 passed.
- Phase 11C live shift/calendar CRUD command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11c-live-shift-calendar-crud.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; shift create/reload/edit/deactivate/reactivate/delete and holiday calendar create with holiday row/reload/edit/deactivate/reactivate/delete completed through browser UI. Screenshots captured as `screenshots/phase11c-live-*.png`.
- RBAC migration command after EFO-014 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0199 applied; shift and holiday-calendar view/create/update/delete permissions are active for superadmin/admin role family.
- Backend regression command after EFO-015/EFO-016 fixes: `venv/bin/python manage.py test hrms.tests.test_services.HrmsServiceTests.test_shift_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_holiday_calendar_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_employee_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_contract_service_excludes_deleted_when_including_inactive hrms.tests.test_services.HrmsServiceTests.test_organization_unit_service_excludes_deleted_when_including_inactive --keepdb`
- Result: 5 passed.
- Phase 11D live HRMS onboarding command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11d-live-onboarding-adoption.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; onboarding preview, recommended adoption, repeat-adoption idempotence, adopted leave-type rename/restore, and mobile layout evidence completed through browser UI. Screenshots captured as `screenshots/phase11d-live-*.png`.
- RBAC migration command after EFO-017 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0200 applied; HRMS onboarding view/adopt/update permissions are active for superadmin/admin role family.
- Backend regression command after EFO-018 fix: `venv/bin/python manage.py test hrms.tests.test_onboarding --keepdb`
- Result: 9 passed.
- Phase 11E live leave runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11e-live-leave-runtime.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; onboarding adoption precondition, employee/contract setup, leave policy advanced rule edit/restore, policy entitlement bootstrap, opening ledger evidence, mobile layout, and cleanup completed through browser UI. Screenshots captured as `screenshots/phase11e-live-*.png`.
- RBAC migration command after EFO-019 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0201 applied; HRMS leave policy view/update, leave balance view, and leave ledger view permissions are active for superadmin/admin role family.
- Phase 11F live attendance runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11f-live-attendance-runtime.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; payroll period prerequisite, employee/contract setup, daily attendance grid load/save, attendance CSV validate/commit, monthly summary desktop/mobile evidence, and cleanup completed through browser UI. Screenshots captured as `screenshots/phase11f-live-*.png`.
- RBAC migration command after EFO-020 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0202 applied; attendance-entry view/create/update, attendance-import view/create, attendance payroll-period view, and attendance summary view permissions are active for superadmin/admin role family.
- Backend command after EFO-021 fix: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11G payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; seeded payroll runtime data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11G live payroll run runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://localhost:4200 npx playwright test playwright/tests/entity-formation-phase11g-live-payroll-run-runtime.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; payroll run create, calculate, employee trace drawer, and mobile detail completed through browser UI. Screenshots captured as `screenshots/phase11g-live-*.png`.
- Phase 11G cleanup command: deleted the untagged browser-created payroll run for `SEP-2026-PW-E2E`; tagged seeded payroll baseline runs remain for reruns.
- Typecheck command after EFO-023 fix: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11G: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11H payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll close data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11H live payroll close runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4302 npx playwright test playwright/tests/entity-formation-phase11h-live-payroll-close-runtime.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; submit, approve, post, payment handoff, payment reconcile, payment batch list/detail/export/paid, payroll register, ESS payslip, and mobile close evidence completed through browser UI. Screenshots captured as `screenshots/phase11h-live-*.png`.
- Typecheck command after EFO-024/EFO-025 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11H: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11I payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll correction and payment-batch exception data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11I live payroll correction runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4303 npx playwright test playwright/tests/entity-formation-phase11i-live-payroll-correction-runtime.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; payroll reversal, invalid-batch approval block, duplicate active batch creation block, validated batch cancel, exported batch failed, failed batch paid recovery, and mobile correction evidence completed through browser UI. Screenshots captured as `screenshots/phase11i-live-*.png`.
- Typecheck command after EFO-026 fix: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11I: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11J payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll export/audit/permission data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11J live payroll export/audit/permission runtime command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4304 npx playwright test playwright/tests/entity-formation-phase11j-live-payroll-export-audit-permissions.spec.ts --project=chromium --reporter=list`
- Result: 2 passed; payroll report export, payment-batch export history, payment-batch CSV re-download, ESS list/detail payslip PDF downloads, restricted report export lock, restricted run action locks, restricted payment-batch action locks, and mobile audit evidence completed through browser UI. Screenshots captured as `screenshots/phase11j-live-*.png`.
- Typecheck command after EFO-027 fix: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11J: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11K payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll admin setup data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11K live payroll admin setup command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4305 npx playwright test playwright/tests/entity-formation-phase11k-live-payroll-admin-setup.spec.ts --project=chromium --reporter=list`
- Result: 2 passed; payroll period editor normalization, component create/update, policy and rule creation, statutory scheme/registration creation, salary-structure versioning, readiness preview, restricted setup mutation locks, and mobile setup evidence completed through browser UI. Screenshots captured as `screenshots/phase11k-live-*.png`.
- Typecheck command after EFO-028/EFO-029/EFO-030 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11K: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11L live statutory setup negative-path command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4306 npx playwright test playwright/tests/entity-formation-phase11l-live-payroll-setup-negative-paths.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; statutory scheme duplicate feedback, inactive scheme recovery, statutory registration duplicate feedback, inactive registration recovery, and mobile statutory setup evidence completed through browser UI. Screenshots captured as `screenshots/phase11l-live-statutory-*.png` and `screenshots/phase11l-live-payroll-setup-negative-paths-mobile.png`.
- Typecheck command after EFO-031 fix: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11L: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11M payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll setup assignment/readiness data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11M live payroll setup assignment/readiness command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4307 npx playwright test playwright/tests/entity-formation-phase11m-live-payroll-assignment-readiness.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; contract payroll profile creation, salary assignment validation/create, statutory contract profile validation/create, recurring pay item validation/create, one-time pay item validation/create, runtime readiness recheck, and mobile readiness evidence completed through browser UI. Screenshots captured as `screenshots/phase11m-live-*.png`.
- Typecheck command after EFO-032/EFO-033 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11M: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11N payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll edit/recovery/permission data for entity id 187, financial year id 175, and period `SEP-2026-PW-E2E`.
- Phase 11N live payroll setup edit/recovery/permission command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4308 npx playwright test playwright/tests/entity-formation-phase11n-live-payroll-edit-recovery-permissions.spec.ts --project=chromium --reporter=list`
- Result: 2 passed; contract profile edit, salary assignment edit, contract statutory inactive/recovery, recurring pay item inactive/recovery, one-time pay item inactive/recovery, runtime readiness refresh, mobile evidence, and restricted setup mutation locks completed through browser UI. Screenshots captured as `screenshots/phase11n-live-*.png`.
- Typecheck command after EFO-034/EFO-035 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11N: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11O payroll data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed payroll archive/duplicate/scope data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11O live payroll setup archive/duplicate/scope command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4309 npx playwright test playwright/tests/entity-formation-phase11o-live-payroll-archive-duplicates-scope.spec.ts --project=chromium --reporter=list`
- Result: 2 passed; duplicate active contract profile feedback, salary assignment overlap feedback, close-previous rollover, contract profile archive/recovery, and alternate-branch scope isolation completed through browser UI. Screenshots captured as `screenshots/phase11o-live-*.png`.
- Typecheck command after EFO-036/EFO-037/EFO-038 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11O: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11P payroll/HRMS data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed HRMS/payroll setup data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11P live HRMS setup audit/delete-confidence command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4310 npx playwright test playwright/tests/entity-formation-phase11p-live-hrms-audit-delete-confidence.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; Organization Units, Employees, Employment Contracts, Shifts, and Holiday Calendars show Last Updated audit values and soft-delete/delete-confidence dialog copy through browser UI. Screenshots captured as `screenshots/phase11p-live-*.png`.
- Typecheck command after EFO-039/EFO-040 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11P: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11Q payroll/HRMS data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed HRMS/payroll setup data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11Q live HRMS mobile table-density command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4311 npx playwright test playwright/tests/entity-formation-phase11q-live-hrms-mobile-table-density.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; Organization Units, Employees, Employment Contracts, Shifts, and Holiday Calendars contain wide tables inside horizontal scroll wrappers on a 390px mobile viewport, keep Last Updated reachable, and keep soft-delete dialogs reachable through browser UI. Screenshots captured as `screenshots/phase11q-live-*.png`.
- Typecheck command after Phase 11Q: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11Q: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11R payroll/HRMS data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed HRMS/payroll setup data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11R live accessibility/keyboard command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4312 npx playwright test playwright/tests/entity-formation-phase11r-live-accessibility-keyboard.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; Entity & Partner Details, Capital Distribution, Organization Units, Payroll Runs, and ESS Payslips passed keyboard activation checks, visible-control accessible-name checks, and serious/critical axe checks. Screenshots captured as `screenshots/phase11r-live-*.png`.
- Typecheck command after EFO-041/EFO-042 fixes: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11R: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11S payroll/HRMS data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed HRMS/payroll setup data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11S live cross-browser command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4313 npx playwright test playwright/tests/entity-formation-phase11s-live-cross-browser-confidence.spec.ts --config=playwright.reports-cross-browser.config.ts --reporter=list`
- Result: 3 passed; Chromium, Firefox, and WebKit all certified Entity & Partner Details ownership keyboard activation, Capital Distribution terms tab keyboard activation, Payroll Runs create-panel keyboard activation and labels, ESS Payslips labels, and Organization Units mobile table scrolling plus soft-delete dialog. Screenshots captured as `screenshots/phase11s-live-*.png`.
- Typecheck command after Phase 11S: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11S: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 11T payroll/HRMS data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll/HRMS performance data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 11T live performance command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4314 npx playwright test playwright/tests/entity-formation-phase11t-live-performance-responsiveness.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; CFO Payables, CFO Receivables, CFO Cash Flow, Payroll Runs, and Organization Units met local page-readiness and API timing guardrails. Screenshots captured as `screenshots/phase11t-live-*.png`.
- Phase 11T metrics capture command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4314 npx playwright test playwright/tests/entity-formation-phase11t-live-performance-responsiveness.spec.ts --project=chromium --reporter=json`
- Result metrics: CFO Payables ready 1041ms, slowest API 387ms (`GET /api/cfo/payables/worklist/`); CFO Receivables ready 355ms, slowest API 278ms (`GET /api/cfo/receivables/worklist/`); CFO Cash Flow ready 245ms, slowest API 144ms (`GET /api/cfo/cash-flow/forecast/`); Payroll Runs ready 542ms, slowest API 384ms (`GET /api/entity/me/entities/187/subentities`); Organization Units ready 524ms, slowest API 363ms (`GET /api/payroll/periods/`).
- Typecheck command after Phase 11T: `npm run typecheck`
- Result: passed.
- Backend command after Phase 11T: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Backend targeted leave-balance command attempted: `venv/bin/python manage.py test hrms.tests.test_api.HrmsApiTests.test_leave_balance_bootstrap_creates_opening_snapshots_from_policy_defaults hrms.tests.test_api.HrmsApiTests.test_leave_balance_bootstrap_prorates_yearly_quota_for_mid_year_joiner --keepdb`
- Result: blocked in this settings profile because `hrms.tests.test_api` imports payroll models while payroll is not in `INSTALLED_APPS`; browser Phase 11E and `manage.py check` passed.
- Backend command after EFO-006 fix: `venv/bin/python manage.py check`
- Result: passed, no issues.
- RBAC migration commands after EFO-007 fix: `venv/bin/python manage.py migrate rbac`, `venv/bin/python manage.py check`
- Result: migrations 0195 and 0196 applied; branch view/create/update/edit/delete permissions are active for superadmin/admin role family; system check passed.
- RBAC migration command after EFO-010 fix: `venv/bin/python manage.py migrate rbac`
- Result: migration 0197 applied; organization-unit view/create/update/delete permissions are active for superadmin/admin role family.
- Post-fix browser rerun command: `npx playwright test playwright/tests/entity-formation-browser-evidence.spec.ts playwright/tests/entity-formation-matrix-browser-evidence.spec.ts --project=chromium --reporter=list`
- Result: 30 passed.
- Typecheck command: `npm run typecheck`
- Result: passed.
- Phase 12D payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 12D live CFO runtime CRUD command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4315 npx playwright test playwright/tests/entity-formation-phase12d-live-cfo-runtime-crud.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; cash-flow adjustment create/delete, month-close task reopen/complete, budget line save, budget variance action-required review, risk queue acknowledgement, management-pack snapshot save, evidence create/review, predictive insight acknowledgement, and scenario approval completed through browser UI. Screenshots captured as `screenshots/phase12d-live-cfo-*.png`.
- Defect EFO-043 found/fixed: CFO Evidence Center returned a server error after risk reviews existed because audit event aggregation reused the evidence-period filter against `CfoRiskReview`, which does not have period fields. Fixed `cfo/services.py` to use a risk-review-specific scope/review-date filter.
- Typecheck command after Phase 12D: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12D: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 12E payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 12E live CFO permission negative-path command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4316 npx playwright test playwright/tests/entity-formation-phase12e-live-cfo-permission-negative.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; browser-certified read-only CFO flags hide or disable cash-flow adjustments, month-close task/lock actions, budget save/review actions, risk review actions, management-pack snapshot/publish actions, evidence create/review actions, insight review actions, and scenario save/approve actions. Screenshots captured as `screenshots/phase12e-live-cfo-readonly-*.png`.
- Defect EFO-044 found/fixed: CFO Management Pack `Save Draft` was a write action but was not disabled when the publish/write permission was absent. Fixed the frontend button guard and backend snapshot-create permission check so draft and published snapshots both require `cfo.management_pack.publish`.
- Typecheck command after Phase 12E: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12E: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 12F payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data for entity id 187, financial year id 175, Head Office subentity id 181, and period `SEP-2026-PW-E2E`.
- Phase 12F live CFO mobile responsive command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4317 npx playwright test playwright/tests/entity-formation-phase12f-live-cfo-mobile-responsive.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; browser-certified CFO Control Tower, Receivables, Payables, Cash Flow, Month Close, Budget vs Actual, Risk Queue, Management Pack, Evidence Center, Predictive Insights, and Scenario Planner at 390x844 mobile viewport. The check verifies key content readiness, no page-level horizontal overflow, tappable action buttons, and contained horizontal scroll for dense finance tables. Screenshots captured as `screenshots/phase12f-live-cfo-*-mobile.png`.
- Defect EFO-045 found/fixed: CFO Evidence Center created page-level horizontal overflow on mobile because long evidence/audit strings were forced onto a single line. Fixed mobile CSS to allow evidence and event row content to shrink and wrap inside the viewport.
- Typecheck command after Phase 12F: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12F: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 12G backend CFO API permission command attempted: `venv/bin/python manage.py test cfo.tests.test_api_permissions --verbosity=2`
- Result: initial run reached Django's interactive prompt because local test database `test_finacc_db` already existed.
- Phase 12G backend CFO API permission command: `venv/bin/python manage.py test cfo.tests.test_api_permissions --verbosity=2 --keepdb`
- Result: 8 passed; direct API attempts by a CFO view-only user were denied with `403` for cash-flow adjustment create/update/delete, month-close complete/reopen/lock/unlock, budget upsert/review, risk review, management-pack snapshot creation, evidence create/review, insight review, and scenario-plan creation. Cash-flow and evidence no-side-effect checks confirmed denied writes did not mutate existing records.
- Phase 12G payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data and created deterministic browser-test fixtures for real read-only CFO user `entity-formation-cfo-readonly@example.com`, CFO probe adjustment id 6, and CFO probe evidence id 4.
- Phase 12G live CFO browser direct API permission-bypass command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4318 npx playwright test playwright/tests/entity-formation-phase12g-live-cfo-api-permission-bypass.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; browser-certified that a real CFO view-only user can open CFO Cash Flow but direct browser `fetch()` write attempts return `403` for cash-flow adjustment create/update/delete, month-close complete/reopen/lock/unlock, budget upsert/review, risk review, management-pack snapshot creation, evidence create/review, insight review, and scenario-plan creation. Screenshots captured as `screenshots/phase12g-live-cfo-api-bypass-readonly-cash-flow.png` and `screenshots/phase12g-live-cfo-api-bypass-results.png`.
- Typecheck command after Phase 12G: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12G: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 12H payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data for entity id 187, financial year id 175, Head Office subentity id 181, and read-only CFO/export probe fixtures.
- Phase 12H live CFO export/audit-history command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4319 npx playwright test playwright/tests/entity-formation-phase12h-live-cfo-export-audit-history.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; browser-certified CSV exports for CFO Management Pack, Evidence Center, and Scenario Planner. The test opens each screen, validates audit/history sections are visible, downloads each CSV, and verifies expected headers/key rows. Screenshots captured as `screenshots/phase12h-live-cfo-management-pack-export-ready.png`, `screenshots/phase12h-live-cfo-evidence-center-export-ready.png`, and `screenshots/phase12h-live-cfo-scenario-planner-export-ready.png`.
- Typecheck command after Phase 12H: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12H: `venv/bin/python manage.py check`
- Result: passed, no issues.
- Phase 12I payroll/CFO data setup command: `venv/bin/python manage.py prepare_playwright_payroll_data --user-email entity-formation-qa@example.com --entity-name "EFO Live Partnership" --json`
- Result: passed; refreshed CFO/payroll data for entity id 187, financial year id 175, Head Office subentity id 181, and CFO drill-down evidence fixtures.
- Defect EFO-046 found/fixed: Month Close checklist emitted stale legacy evidence routes (`/tds`, `/jv`, `/trialbalance`) that are not valid Angular router targets. Fixed the CFO task catalog to route TDS to `/reports/tds`, accrual JV evidence to `/journalvoucher`, and trial balance review to `/reports/financial/trial-balance`; existing month-close task metadata now self-heals when the cockpit initializes.
- Phase 12I live CFO drill-down route command: `EFO_LIVE_ENABLE=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:4320 npx playwright test playwright/tests/entity-formation-phase12i-live-cfo-drilldown-routes.spec.ts --project=chromium --reporter=list`
- Result: 1 passed; browser-certified CFO API/UI drill-down routes for Control Tower cards, management-pack links, receivables/payables sources, month-close evidence routes, risk queue, evidence center, predictive insights, and scenario/forecast/report targets. The test fails on stale `/tds`, `/jv`, or `/trialbalance` emissions and validates every route is nonblank, unrestricted, and not a 404. Screenshots captured as `screenshots/phase12i-live-cfo-drilldown-*.png` for 22 drill-down targets.
- Typecheck command after Phase 12I: `npm run typecheck`
- Result: passed.
- Backend command after Phase 12I: `venv/bin/python manage.py check`
- Result: passed, no issues.
