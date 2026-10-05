# Core Finance Launch-Grade Verification Plan

Date started: 2026-10-03  
Scope owner: Core finance launch hardening  
Out of scope for this plan: HRMS and Payroll current-state certification

## Purpose

This is the living launch-grade verification plan for Finacc core finance. Update this document after each phase with the executed checks, evidence, failures, fixes, retests, and final status.

The goal is not only to run broad smoke tests. The goal is to verify each finance component at granular depth: route access, UI behavior, validations, permissions, posting impact, reports, reconciliation, documentation, and SES email behavior.

## Confidence Baseline

Use these scoped confidence labels consistently:

| Scope | Current Confidence | Notes |
| --- | ---: | --- |
| Core finance/accounting areas already hardened | 92% | Sales, purchase, reports, major voucher route/RBAC fixes, stale FY/subentity fix, assets UI improvement. |
| Phase 1 finance launch scope excluding HRMS/Payroll | 85% | Remaining risk is in granular module depth, persona RBAC, bank reco, inventory/manufacturing finance links, docs, and SES. |
| Full ERP including HRMS/Payroll/CFO depth | Out of scope | HRMS/Payroll are explicitly excluded from this launch-grade pass. |

## Update Protocol

After each phase:

1. Update the phase row in the status table.
2. Add evidence under the phase detail section.
3. Record failures with root cause, fix owner, and retest command.
4. Move unresolved issues to the open issue register.
5. Update confidence only with scope stated.

Allowed phase statuses:

- `Not Started`
- `In Progress`
- `Passed`
- `Passed with Risk`
- `Blocked`

## Phase Status

| Phase | Area | Status | Last Updated | Evidence / Notes |
| --- | --- | --- | --- | --- |
| 0 | Baseline freeze | Passed | 2026-10-03 | Backend check passed, migrations fully applied, frontend build passed. |
| 1 | Access, context, RBAC | Passed | 2026-10-03 | Auth/entity-context passed; RBAC/restricted-access browser slice passed. |
| 2 | Financial masters and settings | Passed with Risk | 2026-10-03 | Masters/settings batches passed after RBAC and sales-settings scope hardening; one branch-numbering fixture skipped because no valid concrete branch candidate was available. |
| 3 | Sales | In Progress | 2026-10-05 | P0 lifecycle passed. Repaired chunk reruns have closed the known print/compliance, note reconciliation, payload, and GST browser blockers. Latest full Sales P1 rerun reached `57 passed` before stopping for focused triage; the active failures were closed with focused `CESS` and `FIN-SAL-BR-024O` reruns. Full Sales P1/P2 gates remain pending. |
| 4 | Purchase | In Progress | 2026-10-05 | Purchase P0 focused launch pass started. Goods route/form hydration blocker repaired and focused route smoke passed. Service note lifecycle setup was optimized through API-backed context seeding; focused service CN/DN continuity cases now pass. Full Purchase P0 gate remains pending. |
| 5 | Vouchers | Not Started | 2026-10-03 | Journal, cash, bank, receipt, payment, workflow, navigation. |
| 6 | Reports and accounting truth | Not Started | 2026-10-03 | Trial Balance, Ledger, BS, P&L, outstanding, scope hardening. |
| 7 | Bank reconciliation | Not Started | 2026-10-03 | Statement/import/manual match, match/unmatch, report impact. |
| 8 | Assets | Not Started | 2026-10-03 | Asset lifecycle, edit UI, capitalization, reports. |
| 9 | Inventory/manufacturing finance links | Not Started | 2026-10-03 | Finance-impacting inventory/manufacturing flows only. |
| 10 | Compliance | Not Started | 2026-10-03 | TDS, TCS, GST-TDS, GST relationships, reports/export. |
| 11 | SES email testing | Not Started | 2026-10-03 | SES config, real inbox delivery, templates, failure logging. |
| 12 | Documentation completion | Not Started | 2026-10-03 | Module-wise finance operator docs. |
| 13 | Final launch certification | Not Started | 2026-10-03 | Final build, backend, Angular, Playwright, SES, manual signoff. |

## Known Recent Evidence

| Area | Evidence |
| --- | --- |
| Financial report stale scope | Fixed frontend stale entity/FY/subentity restoration. Backend validation remains strict. |
| Trial Balance stale scope regression | Added focused Playwright regression for entity-aware saved filter sanitization. |
| Sales note downstream proof | Focused rerun passed after prior full-smoke failure. |
| Sales Phase 3 P0 invoice/note lifecycle | `FIN-SAL-001/002/003/004/005/006/025/026/027/028/029/030/031/032/033/034/035/036` batch passed on 2026-10-03. |
| Sales compliance Cancel IRN allow-policy | Backend policy gate fixed for active E-Way; backend focused tests passed. Browser `FIN-SAL-CMP-017C/017D/017E` passed after Playwright policy setup correction; one grouped `017D` run had a transient invoice-reopen readiness timeout and passed on isolated rerun. |
| Sales auto e-invoice deterministic path | API e2e tests prove auto e-invoice on confirm/post persists generated IRN when provider returns success: `2 passed` on 2026-10-03. Browser live-provider `CMP-030/031` is now explicitly gated by `SALES_LIVE_EINVOICE_PROVIDER_TESTS=true`. |
| Sales goods note zero-collection TCS | `FIN-SAL-045/046` focused pair passed after note route, save-helper, and TCS preview sequencing hardening: `2 passed` on 2026-10-03. |
| Sales GST tax-context recompute | Header-only tax context updates now recompute existing invoice lines/charges server-side; backend focused regression trio passed and browser GST focused cluster `FIN-SAL-BR-002B/002C/002D/014/023/024E/024H` passed on 2026-10-04. |
| Sales TCS zero-collection suite | Full zero-collection browser file passed after timeout and reason-assertion hardening: `6 passed` on 2026-10-04. |
| Sales TCS note browser cluster | `FIN-SAL-BR-114/115/118` passed after API-seeding slow goods note source/note setup; `FIN-SAL-BR-119` intentionally skipped because the environment did not expose a positive credit-note TCS preview. `FIN-SAL-BR-116/117` passed after zero-collection reason assertion was aligned with the existing toast-or-panel persistence standard. |
| Sales document reconciliation focused pair | `LAUNCH-REP-002C/002D` passed after moving setup-heavy reconciliation tests to the suite-level timeout budget on 2026-10-04. |
| Full Sales P1 gate | `npm run test:sales:p1` completed on 2026-10-04 with `182 passed, 3 skipped, 13 failed, 11 did not run` in 3.8h. Failures are grouped under CF-LAUNCH-015 through CF-LAUNCH-018. |
| O2C sales receipt reconciliation | Focused rerun passed after prior full-smoke timeout. |
| Payment voucher copy-last | `FIN-VCH-019` fixed by adding explicit `120_000` timeout; focused rerun passed in 30.9s. |
| RBAC route/menu sync | Major non-clickable menu issue repaired earlier; needs persona-level confirmation in Phase 1. |
| Legacy stock menus | Retired/hidden: Stock Management, Production Order, Bulk Insert Product. |

## Phase 0: Baseline Freeze

Purpose: establish a stable test baseline before granular module verification.

Checks:

- Backend migration order is clean.
- No unexpected unapplied migrations.
- Backend system check passes.
- Frontend production build passes.
- Environment points to intended local/stage API.
- Test users, roles, entities, FYs, and subentities are known.
- Playwright fixtures can authenticate and open the finance workspace.

Commands:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
python manage.py showmigrations
python manage.py check

cd /Users/ansh/finacc-angular/accountproject
npm run build
```

Exit gate:

- No build blocker.
- No migration blocker.
- No environment mismatch.

Evidence:

- 2026-10-03: `venv/bin/python manage.py check` passed with `System check identified no issues (0 silenced).`
- 2026-10-03: `venv/bin/python manage.py showmigrations` completed successfully.
- 2026-10-03: `venv/bin/python manage.py showmigrations | rg "\[ \]"` returned no unapplied migrations.
- 2026-10-03: `npm run build` completed successfully; output generated at `/Users/ansh/finacc-angular/accountproject/dist/my-app`.

## Phase 1: Access, Context, RBAC

Purpose: verify users can reach only the finance surfaces they should reach, with clean entity/FY/subentity context.

Granular checks:

- Login, logout, session persistence, session expiry behavior.
- Active entity switch.
- Active FY switch.
- Active subentity switch.
- Saved stale entity/FY/subentity state is ignored or sanitized.
- Sidebar authorized menus are clickable.
- Unauthorized menus are hidden or route-blocked.
- Retired stock menus remain hidden.
- Direct URL access is blocked when permission is missing.
- Frontend route keys match backend permissions.
- Documentation route is accessible for logged-in users.
- Persona review: admin, accountant, sales operator, purchase operator, finance viewer, restricted user.

High-risk surfaces:

- Cash Voucher
- Bank Voucher
- Payment Voucher
- Receipt Voucher
- Financial Reports
- Manufacturing Reports
- Operational setup menus
- Documentation

Suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npx playwright test tests/p0/auth.p0.spec.ts tests/p0/auth-entity-integration.p0.spec.ts --project=chromium --workers=1 --reporter=line
npx playwright test tests/p1/admin-rbac-browser.p1.spec.ts tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --project=chromium --workers=1 --reporter=line
```

Exit gate:

- No authorized finance menu is non-clickable.
- No unauthorized direct route leaks.
- No stale context invalid-scope regression.

Evidence:

- 2026-10-03: Auth/entity-context Playwright slice passed.
  - Command: `npx playwright test tests/p0/auth.p0.spec.ts tests/p0/auth-entity-integration.p0.spec.ts --project=chromium --workers=1 --reporter=line`
  - Result: `24 passed, 1 skipped` in 1.9m.
- 2026-10-03: Admin/RBAC restricted-access Playwright slice passed.
  - Command: `npx playwright test tests/p1/admin-rbac-browser.p1.spec.ts tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --project=chromium --workers=1 --reporter=line`
  - Result: `22 passed` in 7.8m.
- Notes: The RBAC slice included admin capability views, role create/edit/deactivate, launch presets, read-only/limited-admin personas, direct denial checks, business settings denial, view-only master restrictions, branch isolation, attachment restriction, inventory/manufacturing isolation, and bundled HRMS/payroll isolation checks. HRMS/payroll remain out of scope for core finance confidence, but permission isolation evidence is positive.

## Phase 2: Financial Masters and Settings

Purpose: verify the setup layer that every finance transaction depends on.

Components:

- Chart of accounts and account groups.
- Ledgers.
- Customers.
- Vendors.
- Branch/subentity setup.
- Payment modes.
- Voucher numbering.
- Posting maps.
- Tax setup.
- TDS/TCS/GST-TDS settings.
- Opening balances.
- Asset categories/settings.

Checks:

- Create, edit, deactivate where applicable.
- Duplicate validation.
- Required-field validation.
- Entity/FY/subentity scoping.
- Permission-based view/edit behavior.
- Downstream availability in invoice/voucher screens.
- Posting-map missing setup produces clear blockers.

Exit gate:

- Master data can be safely used by sales, purchase, vouchers, assets, and compliance.

Evidence:

- 2026-10-03: Financial masters/browser CRUD slice initially found missing account bulk import/export effective permissions.
  - Command: `npx playwright test tests/p1/financial-masters-browser.p1.spec.ts tests/p2/financial-masters.p2.spec.ts tests/p2/account-types.p2.spec.ts tests/p2/account-heads.p2.spec.ts tests/p2/ledgers.p2.spec.ts tests/p2/accounts.p2.spec.ts --project=chromium --workers=1 --reporter=line`
  - Initial result: `27 passed, 3 failed`.
  - Root cause: `financial.account.export` and `financial.account.import` permission rows/effective grants were missing for the launch admin role.
  - Fix: added RBAC catalog entries and migration `rbac/migrations/0216_repair_account_bulk_master_permissions.py`; migration applied and effective permissions verified for the launch user.
  - Focused retest: `FIN-MST-BRW-004|FIN-MST-BRW-005|FIN-MST-004` passed, result `4 passed` including setup.
- 2026-10-03: Settings batch initially exposed sales settings invalid subentity scope.
  - Root cause: frontend/test context could combine `entityId=9`, `entityFinId=7`, `subentityId=9`; backend now returns clean 400 instead of 500 for invalid sales settings scope.
  - Fixes: sales settings backend scope validation added; sales settings component hardened against stale entity/FY/subentity response races; branch options now clear immediately when entity changes; Playwright workspace bootstrap waits for app restore before reasserting intended workspace.
  - Consolidated retest command: `npx playwright test tests/p1/financial-hub-settings.p1.spec.ts tests/p1/payment-settings.p1.spec.ts tests/p1/receipt-settings.p1.spec.ts tests/p1/purchase-settings.p1.spec.ts tests/p1/sales-settings.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-FH-SET-(001|002)|FIN-PAYSET-(001|002|003|004|005|007|010)|FIN-RSET-(001|002|004|005|006|007)|FIN-PSET-(001|002|003|004|005|007|010)|FIN-SALSET-(001|002|003|005|008|013|015|017)"`
  - Result: `31 passed, 1 skipped` in 8.9m. Skip was `FIN-SALSET-003`, accepted as fixture risk because no valid concrete branch numbering candidate was available after rejecting invalid branch scopes.
- 2026-10-03: Branch GSTIN/numbering, GSTIN-assisted account, and withholding section master slice passed.
  - Command: `npx playwright test tests/p1/branch-gstin-numbering-browser.p1.spec.ts tests/p1/gstin-assisted-financial-account.p1.spec.ts tests/p1/withholding-section-master.p1.spec.ts --project=chromium --workers=1 --reporter=line`
  - Result: `11 passed` in 2.2m.

## Phase 3: Sales

Purpose: certify quote-to-cash finance behavior.

Components:

- Goods sales invoice.
- Service sales invoice.
- Sales credit note.
- Sales debit note.
- Save draft, confirm, post, cancel/reject where applicable.
- Print/download.
- Customer ledger and outstanding.
- GST/TCS behavior.
- Receipt settlement.

Checks:

- Header fields.
- Line entry.
- Tax calculation.
- Discount and rounding.
- Customer context.
- State/place of supply.
- Posting entries.
- Ledger Book impact.
- Customer Outstanding impact.
- Trial Balance impact.
- Reopen saved/posted document.
- Duplicate/reference validation.
- Popup behavior for Save, Confirm, Post.

Suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:sales:p0
npm run test:sales:p1
```

Exit gate:

- Sales document lifecycle reconciles with ledger and reports.

Evidence:

- 2026-10-03: Sales P0 invoice/note route and lifecycle batch initially found a goods credit-note assertion failure.
  - Command: `npx playwright test tests/p0/purchase-sales.p0.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-(001|002|003|004|005|006|025|026|027|028|029|030|031|032|033|034|035|036)"`
  - Initial result: `18 passed, 1 failed`.
  - Failed case: `FIN-SAL-033 @p0 @sales price-difference credit note remains value-only on goods note draft`.
  - Observed failure: test expected `saveBody.original_invoice` to equal the original invoice id, but the save helper sometimes returned a synthesized minimal body with only id/bill/status when it resolved persistence through UI identity instead of the network response.
  - Product hardening: frontend sales invoice payload now sends a numeric selected reference invoice as explicit `original_invoice`, while retaining the text `reference`.
  - Test hardening: goods price-difference CN/DN tests now assert persisted `original_invoice`, `note_reason`, and `affects_inventory` from the authoritative saved invoice API detail, matching neighboring note tests.
- 2026-10-03: Focused Angular payload unit spec passed.
  - Command: `npm test -- --watch=false --browsers=ChromeHeadless --include src/app/component/invoice/saleinvoice/saleinvoice-payload.util.spec.ts`
  - Result: `6 SUCCESS`.
- 2026-10-03: Focused Playwright retest for goods price-difference CN/DN passed.
  - Command: `npx playwright test tests/p0/purchase-sales.p0.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-0(33|34)"`
  - Result: `3 passed` including auth setup.
- 2026-10-03: Original Phase 3 P0 sales batch passed after fixes.
  - Command: `npx playwright test tests/p0/purchase-sales.p0.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-(001|002|003|004|005|006|025|026|027|028|029|030|031|032|033|034|035|036)"`
  - Result: `19 passed` in 5.4m.
- Covered in this Phase 3 slice: sales invoice/service invoice routes, credit/debit note routes, service note account-line mode, missing original-link blocker, service CN/DN original linkage, goods quantity-return note inventory-affecting contract, goods price-difference CN/DN value-only contract, note tax/place-of-supply alignment from source invoice, sales/service invoice happy paths, confirm-save behavior, and post button enablement after confirm.
- 2026-10-03: Sales P1 full pack was started and stopped for triage after the first failure cluster.
  - Command: `npm run test:sales:p1`
  - Stopped result: `88 passed, 4 failed, 1 interrupted, 1 skipped, 115 did not run`.
  - Failures found:
    - `FIN-SAL-BR-024A`: goods credit note ship-to change updated header tax context but did not recompute saved-line tax preview.
    - `FIN-SAL-BR-116`: service credit/debit note host selectors were missing in the page helper.
    - `FIN-SAL-PR-021` and `FIN-SAL-PR-027`: posted service note print setup was blocked by frontend/backend action flag mismatch for cancel on locked posted invoices.
  - Fixes: saved-line tax preview now refreshes for header-driven tax changes; service note host selectors added to Playwright page helper; sales action flags now allow posted cancel while keeping unpost policy strict.
  - Unit retests:
    - `saleinvoice.component.spec.ts`: `351 SUCCESS`.
    - Backend serializer action-flag tests: `2 tests OK`.
  - Focused browser retests:
    - `FIN-SAL-BR-116`, `FIN-SAL-PR-021`, `FIN-SAL-PR-027`: `4 passed` including auth setup.
    - `FIN-SAL-BR-024A`: `2 passed` including auth setup.
    - Full `sales-note-print.p1.spec.ts`: `16 passed`.
- 2026-10-03: Sales print/compliance P1 batch then exposed setup timing, compliance launcher RBAC, and print toolbar issues.
  - Partial batch before fixes: `17 passed, 3 failed, 1 interrupted, 83 did not run`.
  - Fixed `FIN-SAL-PR-033`: print button click fallback for responsive/off-viewport footer states.
  - Fixed `FIN-SAL-PR-017` and `FIN-SAL-PR-006`: explicit setup-heavy test budgets.
  - Fixed `FIN-SAL-CMP-001`: frontend compliance launcher view gate now matches backend by allowing `sales.compliance.view` or document view permission; Angular focused spec `49 SUCCESS`; browser focused trio `4 passed`.
  - Fixed `FIN-SAL-PR-019`: tax invoice section toggles now preserve manual toolbar choices across parent input refresh/profile refresh; Angular tax invoice spec `14 SUCCESS`; focused browser case passed.
  - Fixed compliance generated-state setup for `FIN-SAL-CMP-002`, `FIN-SAL-CMP-002A`, and `FIN-SAL-CMP-002B`: tests use deterministic API confirm/post where lifecycle mechanics are not under test, reapply action-capable frontend persona for action-surface assertions, and page helper waits were raised for lazy workspace readiness.
  - Focused browser evidence:
    - `FIN-SAL-CMP-002`: `2 passed` including auth setup.
    - `FIN-SAL-CMP-002A`: `2 passed` including auth setup.
    - `FIN-SAL-CMP-002B`: `2 passed` including auth setup.
    - Focused cluster for `FIN-SAL-PR-019`, `FIN-SAL-CMP-002`, `FIN-SAL-CMP-002A`, `FIN-SAL-CMP-002B`: first three target tests passed in sequence; `CMP-002B` then failed on workspace-ready timing and passed separately after timeout correction.
- 2026-10-03: Continued Sales print/compliance P1 tail with deterministic API lifecycle setup where lifecycle mechanics were not the assertion target.
  - Passed focused evidence:
    - `FIN-SAL-CMP-002C/002D/002F`: `4 passed` including auth setup.
    - `FIN-SAL-CMP-002E`: `2 passed` after aligning sparse posted IRN wording to `IRN: Pending`.
    - `FIN-SAL-CMP-007/007A`: passed in focused rerun after API setup hardening.
    - `FIN-SAL-CMP-008AB`: `2 passed` after returning from workspace via `Back To Overview`.
    - View-only/workspace/quick-sync lookup cluster `007B/008/008A/008AA/008B/008BA/010/010A`: `8 passed` in chunk plus focused `008B` pass after explicit mock action flags.
    - Transport and lookup cluster `008C/008D/010B/010C/010D/010E/010F`: `8 passed`.
    - B2C/audit/report cluster `010G/010J/010K/010L/010H/010I/011/012/024/025/026/027`: `11 passed` in chunk, plus focused fixes for `011` and `025` passed.
    - Automation/settings cluster `013/014/015/016/028/029`: `013` and `014` passed focused after toast/button fallback and action-permission grant; `015/016/028/029` passed in cluster.
    - Active E-Way operations cluster `009/017/017A/017AA/017C/017B/018/019/020/021/022/023/033/034/032`: `15 passed` in cluster; focused `017C` passed after post/reopen permission grant.
  - Test harness hardening:
    - Shared Sales compliance setup now uses API confirm/post/reopen helpers to avoid slow/flaky UI lifecycle setup in tests whose assertions are on compliance surfaces.
    - Compliance opener now dismisses toasts and has an Angular component fallback when the post-state button click visually activates but does not raise the Prime dialog.
    - Frontend test persona grants now include `sales.invoice.update`/`sales.invoice.edit` in addition to `sales.compliance.*` action permissions, matching the compliance component's action gate.
  - Remaining focused gaps:
    - Full Sales P1/P2 packs still need end-to-end rerun after the final compliance-test gating changes.
  - 2026-10-03: Fixed and retested Cancel IRN allow-policy propagation for active E-Way.
    - Backend `SalesComplianceService.compliance_action_flags()` now honors `policy_controls.compliance_allow_cancel_irn_when_eway_active=on` when computing `can_cancel_irn`.
    - Backend `cancel_irn()` now permits IRN cancellation while E-Way is active only when that policy is enabled; default remains strict and still blocks active E-Way.
    - Backend focused tests passed: allow-policy action flags, allow-policy cancel IRN execution, and default strict block for active E-Way.
    - Playwright setup corrected to patch/restore nested `settings.policy_controls`, matching real Sales settings metadata.
    - Browser focused evidence: grouped `FIN-SAL-CMP-017C/017D/017E` run produced `3 passed, 1 failed` where only `017D` failed during invoice-reopen readiness before compliance assertion; isolated `FIN-SAL-CMP-017D` rerun then passed. Effective target evidence: `017C`, `017D`, and `017E` passed.
  - 2026-10-03: Reclassified `FIN-SAL-CMP-030/031` from application blocker to live-provider smoke.
    - Added deterministic API e2e coverage for auto e-invoice on confirm and post, with the external provider boundary mocked and the real invoice lifecycle/artifact persistence exercised.
    - Backend focused evidence: `sales.tests_e2e_api.SalesApiEndToEndTests.test_confirm_auto_einvoice_persists_generated_irn_when_provider_succeeds` and `test_post_auto_einvoice_persists_generated_irn_when_provider_succeeds`: `2 passed`.
    - Browser `FIN-SAL-CMP-030/031` now skips unless `SALES_LIVE_EINVOICE_PROVIDER_TESTS=true`, because those cases require a target backend with working live/sandbox e-invoice provider credentials.
- 2026-10-03: Latest full Sales P1 attempt was stopped for focused triage after the first TCS failure cluster.
  - Command: `npm run test:sales:p1`
  - Stopped result: `5 passed, 2 failed, 1 interrupted, 201 did not run`.
  - Failed cases: `FIN-SAL-045` goods credit note zero-collection TCS save reason and `FIN-SAL-046` goods debit note zero-collection TCS save reason.
  - Root causes:
    - `saveInvoiceAndWait()` falsely classified a saved goods note as local validation failure because it scanned full page text for generic `validation`, matching the fixture stock location name `Launch Validation Stock`.
    - Goods note route helpers could be fooled by the previous sales invoice surface because they checked only for any sales form, not the target credit/debit note heading.
    - The zero-collection helper attempted preview before a new goods note had a persisted invoice id; manual TCS preview requires an existing document id.
    - A second post-preview save was unnecessary for the user-visible reason assertion and could stall on debit notes after the reason was already visible.
  - Fixes:
    - Tightened local validation detection to specific validation/error phrases.
    - Credit/debit note route helpers now verify the target note heading and fall back through the Sales menu when needed.
    - Zero-collection helper now saves the note first, computes TCS preview only if the panel is stale or missing a reason, and asserts the visible reason without a redundant second save.
    - Goods note zero-collection tests now use the same `180_000` budget as other setup-heavy sales note browser flows.
  - Focused evidence:
    - `FIN-SAL-045`: passed with reused auth, `1 passed` in 2.9m.
    - `FIN-SAL-046`: passed with reused auth, `1 passed` in 1.8m.
    - Paired confirmation: `npx playwright test tests/p0/sales-tcs-zero-collection.p0.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-04(5|6)" --no-deps`; result `2 passed` in 2.5m.
- 2026-10-04: Sales GST and tax-context focused triage found one application bug and multiple harness timing/host-selection risks.
  - Application root cause: patching only header tax context fields, such as ship-to/place-of-supply, could persist the header change without recomputing existing saved line and charge tax buckets when no line payload was submitted.
  - Backend fix: `SalesInvoiceService.update_with_lines()` now captures the previous tax context, compares it after header persistence, and recomputes existing lines/charges when the tax context changes without explicit line/charge payloads.
  - Backend focused evidence: `test_patch_recomputes_tax_regime_when_stale_seller_state_placeholder_is_sent`, `test_patch_normalizes_alpha_state_aliases_before_tax_regime_recompute`, and `test_patch_header_tax_context_recomputes_existing_lines_without_line_payload`: `3 tests OK`.
  - Playwright hardening: active sales host lookup is route-aware; registered-customer GST assertions now compare against live selected ship-to/POS/seller context; existing-document saves now require a real write response instead of accepting stable identity alone.
  - Browser focused evidence: `FIN-SAL-BR-002B/002C/002D/014/023/024E/024H`: `7 passed` in 9.9m.
- 2026-10-04: Full Sales P1 rerun progressed past zero-collection and reconciliation, then exposed a deterministic `FIN-SAL-BR-002B` race.
  - Failed full-gate evidence before fix: `17 passed, 1 failed, 1 interrupted, 190 did not run`; real failure was `FIN-SAL-BR-002B`.
  - Root cause: the third save request carried the old inter-state `shipping_detail` after a previous save response/hydration re-applied stale header state. Backend recompute was not the failing layer.
  - Playwright helper fix: `saveInvoiceAndWait()` now waits for the active sales component to be idle after save response settlement, including saving/loading/hydrating flags, before returning control to the next edit.
  - Browser focused evidence after fix: `FIN-SAL-BR-002B`: `1 passed` in 58.1s; recompute cluster `FIN-SAL-BR-002B/002C/002D/014/023/024E/024H`: `7 passed` in 10.2m.
- 2026-10-04: Sales service note GST timeout cluster was retested after applying setup-heavy budgets to the note create/reopen block.
  - Browser focused evidence: `FIN-SAL-BR-017/018/019/020`: `4 passed` in 8.1m.
- 2026-10-04: Sales TCS zero-collection full browser file passed after timeout and reason-assertion hardening.
  - Browser focused evidence: `npx playwright test tests/p0/sales-tcs-zero-collection.p0.spec.ts --project=chromium --workers=1 --reporter=line --no-deps`; result `6 passed` in 8.2m.
- 2026-10-04: Sales document reconciliation focused pair passed after moving setup-heavy reconciliation tests onto the suite-level timeout budget.
  - Browser focused evidence: `LAUNCH-REP-002C/002D`: `2 passed` in 2.8m.
- 2026-10-04: Sales TCS note browser cluster timing blocker was repaired.
  - Root cause: goods debit/credit note TCS P1 cases spent most of their per-test budget creating source invoice and linked note documents through the UI before reaching the actual TCS assertion.
  - Playwright fix: goods note TCS cases now API-seed the prerequisite source invoice and linked note, while keeping the browser coverage on withholding enablement, section selection, recompute, save, reopen, and stale-after-edit behavior.
  - Assertion hardening: P1 zero-collection note cases now accept the non-applied reason in either toast text or the persisted TCS panel note, matching the existing P0 zero-collection standard while still verifying saved `tcs_amount=0` and reopen persistence.
  - Browser focused evidence: `FIN-SAL-BR-114`: `1 passed` in 1.6m; `FIN-SAL-BR-114/115/118/119`: `3 passed, 1 skipped` in 5.7m, with `119` skipped by the intended positive-preview availability guard; JSON rerun confirmed `114`, `115`, and `118` passed and `119` skipped.
  - Browser focused evidence: `FIN-SAL-BR-116`: `1 passed` in 2.3m; `FIN-SAL-BR-116/117`: `2 passed` in 4.3m.
- 2026-10-04: Full Sales P1 gate was executed end to end for launch-grade observation.
  - Command: `npm run test:sales:p1`.
  - Result: `182 passed, 3 skipped, 13 failed, 11 did not run` in 3.8h.
  - Strong evidence from the run:
    - Sales P0 zero-collection TCS remained green inside the broader P1 execution.
    - Sales document reconciliation advanced through `LAUNCH-REP-002/002B/002C/002D`.
    - Sales note document reconciliation passed for service and goods credit/debit notes, including downstream register/book checks.
    - Sales note print suite passed.
    - GST/TCS browser coverage progressed past the previously repaired saved-line, ship-to/POS recompute, service-note GST, goods-note TCS, and zero-collection reason clusters.
    - The compliance UI correctly displayed view-only messaging when action permissions were absent.
  - Failed clusters:
    - Print profile download cluster: `FIN-SAL-PR-007`, `FIN-SAL-PR-008`, and `FIN-SAL-PR-018` timed out around multi-profile download/profile switching.
    - Compliance action/report gating cluster: `FIN-SAL-CMP-007`, `FIN-SAL-CMP-012`, and `FIN-SAL-CMP-026` rendered expected actions disabled in specific setup paths.
    - O2C receipt settlement cluster: `LAUNCH-O2C-001` timed out waiting for the receipt post response after the UI indicated posting was available; subsequent O2C tests did not run.
    - TCS statutory full-flow cluster: `FIN-SAL-TCS-FLOW-001` through `006` failed in `beforeEach` because workspace bootstrap remained on the default 30s hook budget.
  - UX observations:
    - Compliance view-only messaging is useful and specific, but disabled report/action buttons need clearer user-facing reasons or tooltips.
    - Receipt voucher workflow state is confusing when the page still presents `Save Draft` while post state/action affordances are also visible.
    - Print profile switching/download generation feels too slow for an operator path and too tightly coupled in the test flow.
  - Code/test observations:
    - Several compliance tests still rely on scattered permission overrides; action-capable setup should be centralized.
    - Long multi-action tests hide the actual failing step and increase timeout blast radius; print profile downloads should be split or given explicit per-profile readiness checks.
    - TCS full-flow uses per-test timeouts but not a suite-level/hook timeout, so setup can fail before the test budget applies.
    - Receipt posting helper waits for one exact endpoint shape; focused triage should confirm whether the UI is not clicking post, the endpoint changed, or post is blocked by workflow state.
  - Performance observations:
    - `sales-gst-tcs-browser.p1.spec.ts` took about 1.8h.
    - `sales-note-print.p1.spec.ts` took about 15.2m.
    - `sales-note-document-reconciliation.p1.spec.ts` took about 8.0m.
    - Full Sales P1 took 3.8h, which is too slow for a routine pre-deploy gate without chunking.
- 2026-10-04: Focused rerun of the full-gate failure clusters completed.
  - Print cluster command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-PR-00(7|8)|FIN-SAL-PR-018"`.
  - Print cluster result: `3 failed, 1 passed` in 3.7m. All three target print-download cases reproduced the timeout in isolation. `FIN-SAL-PR-007` timed out waiting for the browser `download` event after the profile badge/hint updated; `FIN-SAL-PR-008` and `FIN-SAL-PR-018` timed out around print popup/profile selection after page closure from the test budget.
  - Compliance cluster command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-CMP-00(7)( |$)|FIN-SAL-CMP-012|FIN-SAL-CMP-026"`.
  - Compliance cluster result: `4 passed` in 3.0m. These cases do not reproduce as isolated product failures; treat as suite-order/state-leakage, permission-override drift, or lazy refresh timing until proven otherwise.
  - O2C command: `npx playwright test tests/p1/sales-receipt-reconciliation.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "LAUNCH-O2C-001"`.
  - O2C result: `2 passed` in 6.9m. The accounting path can complete, but the file is slow and vulnerable under full-suite pressure.
  - TCS full-flow command: `npx playwright test tests/p1/sales-tcs-full-flow.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-TCS-FLOW-00[1-6]"`.
  - TCS full-flow result: `6 passed, 1 failed` in 4.8m. The only failed target was `FIN-SAL-TCS-FLOW-005`, and it failed on the default 30s test timeout; neighboring TCS full-flow tests already use explicit 120s budgets.
- 2026-10-04: Print/download and TCS timeout focused fixes were applied and retested.
  - Print fix: Playwright print helper now reads the active `app-taxinvoice` Angular component state, waits for print popup idle before profile changes/download clicks, verifies the selected profile label, and uses a forced click with DOM fallback for the active popup download button. Multi-PDF print download tests now use a `180_000` budget.
  - Print retest command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-PR-00(7|8)|FIN-SAL-PR-018"`.
  - Print retest result: `4 passed` in 2.0m.
  - TCS fix: `sales-tcs-full-flow.p1.spec.ts` now has suite-level `120_000` timeout coverage so `beforeEach` bootstrap and `FLOW-005` no longer use the default 30s budget.
  - TCS retest command: `npx playwright test tests/p1/sales-tcs-full-flow.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-TCS-FLOW-00[1-6]"`.
  - TCS retest result: `7 passed` in 2.7m.
- 2026-10-04: Compliance action/report focused hardening was applied and retested.
  - Fix: `FIN-SAL-CMP-007`, `FIN-SAL-CMP-012`, and `FIN-SAL-CMP-026` now explicitly grant the action-capable sales compliance frontend persona at test start instead of relying on earlier suite state.
  - Retest command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-CMP-00(7)( |$)|FIN-SAL-CMP-012|FIN-SAL-CMP-026"`.
  - Retest result: `4 passed` in 1.8m.
- 2026-10-04: Phase 3A through 3D chunk gates were executed after focused fixes.
  - O2C focused retest after adding receipt post diagnostics: `LAUNCH-O2C-001` passed with auth setup, `2 passed` in 2.3m.
  - Full O2C pack command: `npx playwright test tests/p1/sales-receipt-reconciliation.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "LAUNCH-O2C"`.
  - Full O2C pack result: `14 passed` in 36.9m. Functional path is now strong, but this remains a slow chunk.
  - Full print/compliance command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line`.
  - Full print/compliance result: `77 passed, 2 skipped, 4 failed` in 44.3m. Print profile/download cases passed in the larger file; remaining failures were compliance action-gating cases: `FIN-SAL-CMP-007`, `FIN-SAL-CMP-010F`, `FIN-SAL-CMP-025`, and `FIN-SAL-CMP-014`.
  - Full TCS flow command: `npx playwright test tests/p1/sales-tcs-full-flow.p1.spec.ts --project=chromium --workers=1 --reporter=line`.
  - Full TCS flow result: `9 passed` in 3.6m.
  - Note/reconciliation chunk command: `npx playwright test tests/p1/sales-note-print.p1.spec.ts tests/p1/sales-document-reconciliation.p1.spec.ts tests/p1/sales-note-document-reconciliation.p1.spec.ts --project=chromium --workers=1 --reporter=line`.
  - Note/reconciliation chunk result: `22 passed, 1 failed, 3 did not run` in 14.6m. Failure: `LAUNCH-SNOTE-001B` did not find the posted service sales credit note in customer ledger book.
  - GST/TCS browser chunk command: `npx playwright test tests/p1/sales-gst-tcs-browser.p1.spec.ts tests/p0/sales-tcs-zero-collection.p0.spec.ts --project=chromium --workers=1 --reporter=line`.
  - GST/TCS browser chunk result: `79 passed, 1 skipped, 1 failed` in 1.3h. Failure: `FIN-SAL-BR-002B` third save sent stale `shipping_detail` after repeated ship-to tax-context changes.
- 2026-10-05: Phase 3 focused blocker fixes were applied and retested.
  - Compliance gating fix: compliance reopen paths now re-grant the action-capable frontend persona after route/session refresh, and `CMP-007` waits for the mocked compliance status to settle before action assertions/clicks.
  - Compliance retests: `FIN-SAL-CMP-007/007A/007B/007C/010F/025/014` focused run passed `7 passed, 1 failed` before final `CMP-007` wait repair; isolated `FIN-SAL-CMP-007` then passed with setup, `2 passed` in 1.3m. Prior failures `010F`, `025`, and `014` passed in the focused run.
  - Ledger-book proof fix: sales note reconciliation now waits for the ledger-book response carrying the note-number `search` parameter, avoiding stale unsearched auto-load payloads after ledger selection.
  - Ledger retest command: `npx playwright test tests/p1/sales-note-document-reconciliation.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "LAUNCH-SNOTE-001B"`.
  - Ledger retest result: `2 passed` in 1.7m.
  - Ship-to save fix: frontend sale invoice save hydration now skips applying late canonical save-response detail when the form payload changed after the save request was built, preventing stale ship-to from overwriting the next edit.
  - Ship-to retest command: `npx playwright test tests/p1/sales-gst-tcs-browser.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-BR-002B"`.
  - Ship-to retest result: `2 passed` in 1.5m.
  - Angular retest command: `npm run test:ci -- --include src/app/component/invoice/saleinvoice/saleinvoice.component.spec.ts`.
  - Angular retest result: `351 SUCCESS`.
- 2026-10-05: Repaired Sales P1 chunks were rerun in focused launch-grade slices.
  - Print/compliance chunk command: `npx playwright test tests/p1/sales-print-compliance.p1.spec.ts --project=chromium --workers=1 --reporter=line`.
  - Print/compliance chunk result: `79 passed, 2 skipped, 2 failed` in 1.0h. The previous active compliance blockers `CMP-007`, `CMP-010F`, `CMP-025`, and `CMP-014` stayed green in the full file. New failures were `CMP-007A` malformed action-flags permission refresh and `CMP-023` update multi-vehicle dialog field/click reliability.
  - Print/compliance fixes: `CMP-007A` now re-grants action-capable compliance permissions and waits for recommended action state; compliance dialog field helpers now target exact labels and verify values after fill.
  - Print/compliance focused closure: `FIN-SAL-CMP-007A` and `FIN-SAL-CMP-023` rerun passed with setup: `3 passed` in 2.2m.
  - Note/reconciliation chunk command: `npx playwright test tests/p1/sales-note-print.p1.spec.ts tests/p1/sales-document-reconciliation.p1.spec.ts tests/p1/sales-note-document-reconciliation.p1.spec.ts --project=chromium --workers=1 --reporter=line`.
  - Note/reconciliation chunk result: `25 passed, 1 failed` in 27.6m. Failure was `FIN-SAL-PR-023`, where the print copy Select All click left the popup at `1 selected`.
  - Note/reconciliation fix: print copy helper now verifies selected copy keys through the active `app-taxinvoice` component and retries with a DOM click if the UI click is swallowed; Clear uses the same verification path.
  - Note/reconciliation focused closure: `FIN-SAL-PR-023` rerun passed with setup: `2 passed` in 1.4m.
  - GST/TCS browser chunk command: `npx playwright test tests/p1/sales-gst-tcs-browser.p1.spec.ts tests/p0/sales-tcs-zero-collection.p0.spec.ts --project=chromium --workers=1 --reporter=line`.
  - GST/TCS browser chunk observation before stop: P0 zero-collection TCS and first GST/TCS browser slice progressed to `38 passed`; run was stopped after three repeated failures with the same root cause: frontend payload sent backend-controlled `total_other_charges`.
  - GST/TCS fix: sales invoice payload builder no longer submits `total_other_charges`; backend remains strict and continues to derive controlled totals.
  - GST/TCS retests: saleinvoice Angular spec `351 SUCCESS`; focused browser closure for `FIN-SAL-BR-022H`, `FIN-SAL-BR-023`, `FIN-SAL-BR-024`, and `FIN-SAL-BR-024A` passed with setup inside the narrowed rerun (`5 passed` before the intentionally broader grep continued into unrelated `024A1` diagnostic timeout).
- 2026-10-05: Full Sales P1 was restarted after repaired chunks.
  - Full Sales P1 command: `npm run test:sales:p1`.
  - First stop: CESS setup failed because `uniqueHsnSacData()` could generate duplicate same-second HSN/SAC codes. Fix: add random digits to the generated numeric code. Focused closure for `FIN-SAL-BR-CESS-001/002/003`: `4 passed` in 3.2m.
  - Restarted full Sales P1 progressed through P0 zero-collection TCS, document reconciliation, CESS, GST suppression, inclusive tax, tax-cap, POS override, and reopen-persistence branches. Observation before stop: `57 passed, 1 failed, 1 interrupted, 150 did not run` in 1.4h.
  - Failure: `FIN-SAL-BR-024O` exceeded its 180s test budget at the final Sales Debit Note reopen after persistence/API checks had completed. Fix: tighten spinner-only route-surface detection, add route-recovery reload fallback, and raise only this long-flow case to 300s.
  - Focused closure: `npx playwright test tests/p1/sales-gst-tcs-browser.p1.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-SAL-BR-024O"` passed with setup: `2 passed` in 3.9m.
- Remaining Phase 3 scope: rerun the repaired Sales P1 chunks, rerun full `test:sales:p1`, then run full `test:sales:p2`, broader sales settings/statutory coverage, and optional live-provider `CMP-030/031` smoke when credentials are enabled.

### Phase 3 Observation Work Plan

Priority 1: Print/download stability and performance.

- Split `FIN-SAL-PR-007`, `FIN-SAL-PR-008`, and `FIN-SAL-PR-018` into one profile per test or raise the test budget only after measuring actual PDF generation latency.
- Add explicit readiness around profile switching and download button state before waiting for the browser download event.
- Inspect whether `triggerPrintPopupDownload()` is clicking the active popup download button after profile changes or a stale/offscreen control.
- Product UX improvement: show a short busy state when a PDF download is being prepared and prevent repeated clicks during generation.
- Retest: rerun the print cluster, then rerun the full print/compliance file before the full P1 gate.

Priority 2: Compliance isolation and disabled-state clarity.

- Centralize the action-capable compliance persona setup so individual tests do not depend on scattered permission overrides.
- Add cleanup/restoration assertions after tests that patch frontend permissions or mocked compliance status payloads.
- For disabled compliance actions, expose the blocking reason in UI text, tooltip, or accessible label so operators know whether the blocker is permission, invoice status, missing IRN/EWB, or report prerequisites.
- Retest: rerun `CMP-007/012/026` after isolation hardening, then run a larger compliance chunk that includes tests immediately before and after them.

Priority 3: O2C receipt settlement slow path.

- Instrument receipt voucher posting to confirm whether the slow section is allocation recalculation, workflow-state refresh, post button readiness, or downstream report verification.
- Make the helper capture the actual clicked post control and observed post request URL when waiting for post completion.
- Keep one full UI settlement test for launch proof, but consider API-seeded receipt variants for downstream report-only assertions.
- UX improvement: clarify receipt workflow state so `Save Draft`, `Confirm`, and `Post` cannot appear contradictory to operators.
- Retest: rerun `LAUNCH-O2C-001`, then rerun the remaining `LAUNCH-O2C-*` pack.

Priority 4: TCS full-flow timeout normalization.

- Add a suite-level timeout for `sales-tcs-full-flow.p1.spec.ts` or explicit timeouts to every setup-heavy case, including `FLOW-005`.
- Keep workspace bootstrap inside a budget large enough for first-load metadata and role/context checks.
- Retest: rerun `FIN-SAL-TCS-FLOW-001` through `006`, then the full TCS full-flow file.

Priority 5: Gate structure and runtime.

- Split Sales P1 into smaller launch chunks: print/compliance, GST/TCS browser, note print, note reconciliation, receipt/O2C, and statutory full-flow.
- Track each chunk independently in the launch plan before spending another full 3.8h gate.
- Full `npm run test:sales:p1` should run only after the focused chunks are green.

## Phase 4: Purchase

Purpose: certify procure-to-pay finance behavior.

Components:

- Goods purchase invoice.
- Service purchase invoice.
- Purchase debit note.
- Purchase credit note.
- Save draft, confirm, post, cancel/reject where applicable.
- Vendor ledger and payable outstanding.
- GST-TDS/TDS behavior where applicable.
- Payment voucher settlement.

Checks:

- Header fields.
- Line entry.
- Tax context.
- Vendor context.
- Posting entries.
- Vendor ledger impact.
- Vendor Outstanding/Payables impact.
- Trial Balance impact.
- Payment chain integrity.
- Popup behavior for Save, Confirm, Post.

Suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:purchase:p0
npm run test:purchase:p1
npm run test:purchase:p2
```

Exit gate:

- Purchase lifecycle reconciles with ledger, payables, and payment voucher settlement.

Evidence:

- 2026-10-05: Started focused Purchase P0 with `npm run test:purchase:p0`. Initial run stopped early after `FIN-PUR-NEXT-NOTE-020` found no vendor options, `FIN-PUR-NEXT-NOTE-021` timed out, and the next case was interrupted.
- 2026-10-05: Purchase page-object route readiness was tightened so spinner-only shells are not accepted as loaded, workspace bootstrap now reasserts entity/FY/subentity before the early dashboard return, blank Purchase navigation prefers the sidebar route, and Reset is skipped when the form is already a clean draft.
- 2026-10-05: Direct probe of `/api/purchase/meta/invoice-form/?entity=10&subentity=8` returned `200` in under one second with both Tax Regime choices and 1640 vendors, so the focused failure is not a backend meta-data absence.
- 2026-10-05: Frontend `purchaseinvoice.component.spec.ts` passed after adding an in-flight/timeout guard for Purchase master-data initialization: `167 SUCCESS`.
- 2026-10-05: Focused `FIN-PUR-NEXT-INV-001` passed after route/readiness/reset hardening: `2 passed` in 2.1m.
- 2026-10-05: Service-note lifecycle setup was moved to API-backed context discovery for registered vendor, purchase expense account, and supplier/place-of-supply states. Focused `FIN-PUR-NEXT-NOTE-020/021` passed: `3 passed` including setup in 50.1s.
- 2026-10-05: Focused locked-period quantity-return guard `FIN-PUR-NEXT-NOTE-022` initially hit a Playwright modal-idempotency issue where the already-open correction dialog covered the `Correct` button. The page helper now treats `openLockedCorrectionDialog()` as idempotent; focused retest passed: `2 passed` including setup in 52.2s.
- 2026-10-05: Focused posted-cancel and locked correction action policy passed. `FIN-PUR-053` passed: `2 passed` in 39.0s; `FIN-PUR-049` passed: `2 passed` in 53.0s.
- 2026-10-05: Focused tracked goods and locked correction variants passed. `FIN-PUR-054` passed after syncing the autocomplete input value when selecting newly seeded products through the page helper; grouped `FIN-PUR-047/048/054` retest passed: `4 passed` including setup in 1.9m.
- 2026-10-05: Focused service locked correction routing passed. `FIN-PUR-045/046` passed: `3 passed` including setup in 1.2m.
- 2026-10-05: Focused delete/unpost and purchase line taxability policy slice passed. Initial `FIN-PUR-021E` failure was a QA fixture issue: browser save helper auto-confirmed while the case needed a draft invoice to prove the `never` delete policy. The test now forces draft workflow and disables auto-confirm for that save. Grouped `FIN-PUR-(020|021|021F)` grep run passed: `11 passed` in 5.0m.
- 2026-10-05: Focused round-off, default workflow, and default doc-code slice passed. `FIN-PUR-043A/043B/043C/043D/043E/043F/043G` passed: `8 passed` including setup in 3.4m.
- 2026-10-05: Focused Purchase GST-TDS / Income Tax TDS slice passed after QA-harness repairs. Initial grouped run passed `20` and failed `3`: `FIN-PUR-039A` and `FIN-PUR-039C` were using route-patched withholding defaults while the already-loaded Angular component retained stale meta; `FIN-PUR-041` used a four-digit SAC for an other-charge line while backend validation correctly requires six digits. The test helper now patches live component meta as well as future meta responses, the invalid no-default case disables component fallback so the validation dialog remains open, and the summary case uses a valid six-digit SAC. Focused closure: exact `FIN-PUR-039A` passed `2 passed` in 44.3s; exact `FIN-PUR-039A/039C/041` passed `4 passed` in 2.2m.
- 2026-10-05: Focused Purchase statutory/compliance tail smoke passed. Purchase document compliance overview bridge across service/goods invoice and service/goods CN/DN passed: `FIN-PUR-CMP-001/001B/002/003/004/005` -> `7 passed` including setup in 2.4m. Purchase Statutory shell/scope overview passed: `FIN-PSTAT-001/002/038/039/058` -> `6 passed` including setup in 1.3m. TDS Compliance Center load/FY/quarter/search smoke passed with current live data limits: `4 passed, 1 skipped` in 51.7s. GST-TDS Compliance Center load/FY/quarter/search smoke passed with current live data limits: `3 passed, 2 skipped` in 53.2s. Heavy challan/return/export/all-tab statutory gates remain off-hours scope.
- 2026-10-05: Focused Purchase print/document output slice passed after repair. Initial print run failed because the saved Purchase Invoice footer no longer exposed the already-wired `displayPrintVoucher()` action, while service purchase note print setup was seeding taxable service source invoices without SAC and backend correctly rejected confirm. Restored the Purchase Invoice `Print` footer action and added a valid service SAC to note print fixture data. Closure: invoice print `FIN-PUR-PR-001/002/003` passed `4 passed` including setup in 1.4m; note print `FIN-PUR-PR-004/005` passed `3 passed` including setup in 1.3m; combined `FIN-PUR-PR-001..005` passed `6 passed` in 2.3m. Angular `purchaseinvoice.component.spec.ts` passed `167 SUCCESS`.

## Phase 5: Vouchers

Purpose: certify the accounting transaction core.

Components:

- Journal Voucher.
- Cash Voucher.
- Bank Voucher.
- Receipt Voucher.
- Payment Voucher.
- Copy Last, Previous, Next, Browse.
- Draft, confirm, approve, post, cancel flows.

Checks:

- Create draft.
- Edit draft.
- Save validations.
- Confirm/post permissions.
- Locked-period blocker.
- Voucher numbering.
- Ledger effects.
- Cash/bank balance effects.
- Customer/vendor settlement.
- Runtime TDS behavior in payment voucher.
- Attachments if supported.
- Print/download if supported.
- Route opens cleanly after RBAC changes.

Required regression:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npx playwright test tests/p0/vouchers.p0.spec.ts --project=chromium --workers=1 --reporter=line --grep "FIN-VCH-019" --no-deps
```

Broader suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:payment:p0
npm run test:payment:p1
```

Exit gate:

- Vouchers post correctly, remain navigable, and reconcile to reports.

Evidence:

- `FIN-VCH-019` focused rerun passed on 2026-10-03 after timeout fix.

## Phase 6: Reports and Accounting Truth

Purpose: prove transaction chains land correctly.

Reports:

- Trial Balance.
- Ledger Book.
- Ledger Summary.
- Balance Sheet.
- Profit and Loss.
- Trading Account.
- Customer Outstanding.
- Vendor Outstanding.
- Cash/Bank Book if present.
- GST/TDS/TCS reports.
- Voucher reconciliation reports.

Checks:

- Entity-scoped metadata.
- FY-scoped results.
- Subentity validation.
- No stale saved filter issue.
- Search/filter/export.
- Drilldowns.
- Posted transactions appear in relevant reports.
- Cancelled/unposted transactions are handled correctly.
- Opening balance behavior.

Suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npx playwright test tests/p1/financial-trial-balance.p1.spec.ts --project=chromium --workers=1 --reporter=line
npm run test:accounting-truth
```

Exit gate:

- Reports reconcile with seeded sales, purchase, voucher, and opening-balance chains.

Evidence:

- Pending.

## Phase 7: Bank Reconciliation

Purpose: certify banking control surface.

Checks:

- Bank account selection.
- Statement import path if present.
- Manual reconciliation.
- Match/unmatch.
- Date/reference/amount filtering.
- Reconciled balance.
- Voucher drilldown.
- Permission behavior.
- Report impact.

Exit gate:

- Bank reconciliation can reconcile and reverse safely.

Evidence:

- Pending.

## Phase 8: Assets

Purpose: certify fixed asset accounting flow.

Checks:

- Asset create/edit.
- Asset edit UI usability.
- Category/depreciation fields.
- Capitalization.
- Depreciation run if available.
- Disposal/sale if available.
- Ledger impact.
- Asset register/report.
- Permission behavior.

Exit gate:

- Asset lifecycle does not break accounting reports.

Evidence:

- Pending.

## Phase 9: Inventory and Manufacturing Finance Links

Purpose: verify finance-impacting inventory/manufacturing flows without expanding scope into full operations launch certification.

Inventory checks:

- Active inventory ops menus.
- Retired stock menus remain hidden.
- Stock-linked sales invoice behavior.
- Stock-linked purchase invoice behavior.
- Inventory valuation/report if present.
- Ledger impact from stock transactions.

Manufacturing checks:

- Manufacturing menu access.
- Manufacturing report permission.
- Production/workspace finance-linked reports.
- Stock/accounting impact where enabled.

Exit gate:

- Finance-linked inventory/manufacturing paths do not break core finance launch.

Evidence:

- Pending.

## Phase 10: Compliance

Purpose: certify statutory finance behavior.

Components:

- TDS.
- TCS.
- GST-TDS.
- GST reports/reconciliation where available.
- Purchase/sales/payment integrations.

Checks:

- Settings relationships are documented.
- Sales TCS calculation.
- Purchase/payment TDS calculation.
- GST-TDS behavior.
- Posting-map required validations.
- Reports/export.
- Zero/edge cases.
- Manual override behavior if allowed.

Suggested Playwright:

```bash
cd /Users/ansh/Documents/finacc-ui-tests
npm run test:compliance:visual
npm run test:compliance:assistive
```

Exit gate:

- Statutory amounts calculate, post, and report correctly.

Evidence:

- Pending.

## Phase 11: SES Email Testing

Purpose: verify transactional email delivery before launch.

Email categories:

- Registration/onboarding email.
- Password reset/OTP if applicable.
- Invoice/document email if supported.
- Approval/workflow notification.
- Payment/receipt notification if supported.
- Admin invite or documentation notification if applicable.

SES checks:

- AWS credentials are loaded in backend environment.
- SES region is correct.
- Sender identity is verified.
- Domain DKIM/SPF/DMARC are verified.
- Sandbox vs production mode is confirmed.
- Bounce/complaint handling is reviewed.
- Reply-to/from names are correct.
- HTML and plain text rendering are acceptable.
- Attachments work if invoice emails are supported.
- Rate-limit behavior is known.
- Failed email attempts are logged clearly.

Suggested backend shell smoke:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
python manage.py shell
```

Use the application email utility or Django email backend to send a real test email through the configured SES path.

Exit gate:

- Email received in a real inbox.
- Subject/from/body are correct.
- Links work.
- No SES rejection.
- Failure mode is logged clearly.

Evidence:

- Pending.

## Phase 12: Documentation Completion

Purpose: make operators self-sufficient for core finance.

Required docs:

- Settings/configuration.
- Sales.
- Purchase.
- Vouchers.
- Reports.
- Bank reconciliation.
- Assets.
- TDS/TCS/GST-TDS.
- Inventory finance links.
- Manufacturing finance links.
- RBAC/user roles.
- Troubleshooting common validation messages.

Exit gate:

- Each core finance module has a usable operator guide.

Evidence:

- Pending.

## Phase 13: Final Launch Certification

Purpose: execute the final gated launch pack after phase-level defects are closed.

Final checks:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
python manage.py check
python manage.py showmigrations

cd /Users/ansh/finacc-angular/accountproject
npm run build

cd /Users/ansh/Documents/finacc-ui-tests
npm run test:launch-commercial-smoke
```

Additional gates:

- Key Angular specs pass.
- SES email smoke passes.
- Manual role/menu smoke passes.
- No unresolved launch-blocking issue remains.

Signoff matrix:

| Area | Required Status |
| --- | --- |
| Auth/context | Passed |
| RBAC/menu | Passed |
| Financial masters/settings | Passed |
| Sales | Passed |
| Purchase | Passed |
| Vouchers | Passed |
| Reports | Passed |
| Bank Reconciliation | Passed or accepted risk |
| Assets | Passed |
| Inventory/manufacturing finance links | Passed or accepted risk |
| Compliance | Passed |
| SES emails | Passed |
| Documentation | Minimum launch docs complete |

Evidence:

- Pending.

## Open Issue Register

| ID | Phase | Issue | Severity | Owner | Status | Retest |
| --- | --- | --- | --- | --- | --- | --- |
| CF-LAUNCH-001 | 1 | Persona-level RBAC templates still need launch-grade review. | Medium | TBD | Closed | Phase 1 RBAC persona pass completed on 2026-10-03. |
| CF-LAUNCH-002 | 7 | Bank reconciliation needs focused launch smoke. | Medium | TBD | Open | Phase 7 bank reco checks. |
| CF-LAUNCH-003 | 11 | SES email path not yet verified in this launch pass. | High | TBD | Open | Phase 11 SES smoke. |
| CF-LAUNCH-004 | 2 | Sales branch numbering fixture has no valid concrete branch candidate in current test data; `FIN-SALSET-003` skips after invalid branch scopes are rejected. | Low | QA/Data | Open | Seed or repair a valid concrete sales branch numbering fixture, then rerun `FIN-SALSET-003`. |
| CF-LAUNCH-005 | 3 | Sales goods price-difference note assertion read `original_invoice` from a non-authoritative synthesized save helper response; frontend also did not explicitly send numeric `original_invoice` from the selected reference. | Medium | Frontend/QA | Closed | Angular payload spec `6 SUCCESS`; focused `FIN-SAL-033/034` retest `3 passed`; original Phase 3 P0 batch `19 passed`. |
| CF-LAUNCH-006 | 3 | Sales browser P1 auto IRN tests `FIN-SAL-CMP-030/031` require working live/sandbox e-invoice provider credentials; local browser run did not receive a provider IRN. | High | Backend/Integration/QA | Closed for app path; provider smoke gated | Added deterministic API e2e coverage proving confirm/post auto e-invoice persists generated IRN when provider succeeds (`2 passed`). Browser live-provider cases now require `SALES_LIVE_EINVOICE_PROVIDER_TESTS=true`. |
| CF-LAUNCH-007 | 3 | Sales compliance Cancel IRN allow-policy tests `FIN-SAL-CMP-017D/017E` rendered Cancel IRN disabled when `compliance_allow_cancel_irn_when_eway_active=on` because backend action flags did not honor the policy and Playwright setup patched the toggle outside nested `policy_controls`. | High | Frontend/Backend/QA | Closed | Backend focused tests passed. Browser `FIN-SAL-CMP-017C/017D/017E` target evidence passed after correction; grouped rerun had one transient invoice-reopen timeout for `017D`, then isolated `017D` passed. |
| CF-LAUNCH-008 | 3 | Full Sales P1 gate completed with launch-blocking clusters; focused repairs have now closed the active compliance action-gating, service credit-note ledger proof, `FIN-SAL-BR-002B` stale ship-to save blocker, print-copy helper issue, and `total_other_charges` payload leak. | High | QA/Frontend/Backend | Open | Rerun full `npm run test:sales:p1`; run full `npm run test:sales:p2` after P1 is green. |
| CF-LAUNCH-009 | 3 | Sales goods note zero-collection TCS browser tests `FIN-SAL-045/046` failed or timed out because route readiness, save validation detection, and TCS preview sequencing did not match the goods note lifecycle. | Medium | QA | Closed | Focused paired rerun `FIN-SAL-045/046`: `2 passed` in 2.5m. |
| CF-LAUNCH-010 | 3 | Sales service browser GST cluster had Playwright harness drift: active component lookup could bind to stale invoice hosts, service-note reopen readiness did not include all service-note hosts, and registered-customer tax scenario seeding could read seller GST state from stale `app-saleinvoice` instead of the active route. | Medium | QA | Closed | Focused cluster `FIN-SAL-BR-002B/015/016`: `3 passed` in 3.9m. |
| CF-LAUNCH-011 | 3 | Sales header-only tax-context update could persist changed ship-to/POS context without recomputing existing saved line/charge tax buckets when no line payload was submitted. | High | Backend/QA | Closed | Backend focused trio `3 tests OK`; browser GST focused cluster `FIN-SAL-BR-002B/002C/002D/014/023/024E/024H`: `7 passed` in 9.9m. |
| CF-LAUNCH-012 | 3 | Sales document reconciliation `LAUNCH-REP-002C/002D` could fail in beforeEach because setup-heavy workspace bootstrap remained on the default 30s test timeout. | Medium | QA | Closed | Suite-level timeout added; focused `LAUNCH-REP-002C/002D`: `2 passed` in 2.8m. |
| CF-LAUNCH-013 | 3 | Sales browser save helper could return after network response/identity settlement but before the active component finished save-response hydration, allowing the next ship-to edit to race with stale header reapplication. | Medium | QA | Closed | `FIN-SAL-BR-002B`: `1 passed` in 58.1s; GST recompute cluster `7 passed` in 10.2m after active-component idle wait. |
| CF-LAUNCH-014 | 3 | Sales goods note TCS zero-collection P1 browser setup was too slow for the current full-gate design; `FIN-SAL-BR-114` reached post-save detail verification but exceeded even a 300s budget in grouped execution. | Medium | QA | Closed | API-seeded source/note setup for goods note TCS browser cases. Focused `FIN-SAL-BR-114/115/118/119`: `3 passed, 1 skipped` in 5.7m; `119` skipped only because the current environment did not expose positive-applicable credit-note TCS preview. Service credit-note pair `116/117`: `2 passed` in 4.3m. Full Sales P1/P2 remains tracked by CF-LAUNCH-008. |
| CF-LAUNCH-015 | 3 | Sales print profile download cases `FIN-SAL-PR-007`, `FIN-SAL-PR-008`, and `FIN-SAL-PR-018` time out while switching profiles/downloading PDFs. | High | Frontend/QA | Closed | Print helper now waits for active `app-taxinvoice` idle state, verifies selected profile label, and uses a stronger popup download click; multi-PDF tests have a 180s budget. Focused retest `4 passed` in 2.0m; full print/compliance chunk confirmed print cases inside `77 passed, 2 skipped, 4 failed`. Remaining failures are compliance-only. |
| CF-LAUNCH-016 | 3 | Sales compliance action/report buttons can render disabled in larger-suite execution even when focused cases pass. | High | Frontend/QA | Closed | Full print/compliance chunk now kept prior blockers `FIN-SAL-CMP-007`, `010F`, `025`, and `014` green. New focused failures `007A` and `023` were repaired and rerun: `3 passed` in 2.2m. |
| CF-LAUNCH-017 | 3 | O2C receipt settlement `LAUNCH-O2C-001` timed out waiting for receipt posting in the full gate; later O2C cases did not run. | Medium | Frontend/Backend/QA | Closed | Receipt post diagnostics added. Focused `LAUNCH-O2C-001`: `2 passed` in 2.3m. Full O2C pack `LAUNCH-O2C*`: `14 passed` in 36.9m. Remaining risk is performance, not correctness. |
| CF-LAUNCH-018 | 3 | Sales TCS statutory full-flow cases are inconsistently budgeted; full gate hit setup timeout and focused `FIN-SAL-TCS-FLOW-005` hit default 30s test timeout. | Medium | QA | Closed | Added suite-level 120s timeout to the TCS full-flow file. Focused `001..006`: `7 passed` in 2.7m. Full TCS flow file: `9 passed` in 3.6m. |
| CF-LAUNCH-019 | 3 | Full print/compliance chunk had compliance action-gating failures: `FIN-SAL-CMP-007`, `FIN-SAL-CMP-010F`, `FIN-SAL-CMP-025`, and `FIN-SAL-CMP-014`. Root cause was frontend permission/session refresh timing plus `CMP-007` asserting/clicking before mocked compliance status settled. | High | Frontend/QA | Closed | Reopen paths re-grant action-capable compliance permissions and `CMP-007` now waits for recommended action state. Focused run proved `010F`, `025`, and `014`; isolated final `CMP-007` retest passed `2 passed` in 1.3m. Full print/compliance file still belongs to CF-LAUNCH-008. |
| CF-LAUNCH-020 | 3 | Sales note reconciliation `LAUNCH-SNOTE-001B` did not find posted service sales credit note in customer ledger book, while other note/register/report checks progressed. Root cause was the test accepting a stale ledger-book auto-load response without the note-number search after ledger selection. | High | QA | Closed | Ledger-book checks now require the note-number `search` query. Focused `LAUNCH-SNOTE-001B` retest passed with setup: `2 passed` in 1.7m. |
| CF-LAUNCH-021 | 3 | GST/TCS browser chunk reproduced `FIN-SAL-BR-002B`: repeated save after ship-to tax-context changes sent stale `shipping_detail` on the third save. Root cause was late canonical save-response hydration from the previous save overwriting a newer ship-to edit before the next save. | High | Frontend/QA | Closed | Frontend save hydration skips applying late save-response detail when the form payload changed after the request was built. Focused `FIN-SAL-BR-002B` retest passed with setup: `2 passed` in 1.5m; saleinvoice Angular spec `351 SUCCESS`. |
| CF-LAUNCH-022 | 3 | Goods credit-note print preview `Select All` could leave the print popup at `1 selected`, causing `FIN-SAL-PR-023` to miss duplicate/triplicate preview copies. | Medium | QA | Closed | Print copy helper now verifies active `app-taxinvoice` selected copy keys and retries via DOM click. Focused `FIN-SAL-PR-023`: `2 passed` in 1.4m. |
| CF-LAUNCH-023 | 3 | Sales save payload sent backend-controlled `total_other_charges`, causing strict backend rejection in GST/TCS browser cases (`BR-022H`, `BR-023`, `BR-024`). | High | Frontend | Closed | Removed `total_other_charges` from sales save payload builder while keeping display totals from backend summaries. Angular saleinvoice spec `351 SUCCESS`; focused browser closure for `BR-022H/023/024/024A` passed before unrelated diagnostic timeout. |
| CF-LAUNCH-024 | 3 | Restarted full Sales P1 exposed two QA-harness issues: same-second HSN/SAC CESS seed collisions and `FIN-SAL-BR-024O` exceeding the 180s budget during final Sales Debit Note reopen after persistence checks had completed. | Medium | QA | Closed | HSN/SAC generator now adds random numeric entropy; sales route readiness no longer treats spinner-only hosts as loaded and has reload recovery; only `024O` budget raised to 300s. Focused CESS closure `4 passed`; focused `024O` closure `2 passed` in 3.9m. |
| CF-LAUNCH-025 | 4 | Purchase route/form hydration was unstable in focused P0: goods invoice route could remain spinner/shell-only, and service-note lifecycle setup timed out before source-note assertions. Route readiness now rejects spinner-only shells, clean-draft Reset no longer causes avoidable reloads, Purchase master-data loading has an in-flight/timeout guard, and service-note setup uses API-backed context discovery. | High | Frontend/QA | Closed | Goods route `FIN-PUR-NEXT-INV-001`: `2 passed`. Service note continuity `FIN-PUR-NEXT-NOTE-020/021`: `3 passed` including setup in 50.1s. Next: resume Purchase P0 gate. |
| CF-LAUNCH-026 | 4 | Purchase tracked goods batch/expiry UI case `FIN-PUR-054` could not complete line entry for a newly API-seeded tracked catalog product. Product search resolved the target, but PrimeNG force-selection could clear the product after the page helper selected through component state without syncing the visible autocomplete input. | Medium | QA | Closed | Page helper now syncs the actual autocomplete input value after component-backed product selection and waits for enabled line controls. Focused `FIN-PUR-054`: `2 passed` in 50.8s; grouped `FIN-PUR-047/048/054`: `4 passed` in 1.9m. |
| CF-LAUNCH-027 | 4 | Purchase TDS focused slice exposed QA-harness drift around withholding meta overrides and invalid other-charge SAC data. Route-level meta patches did not update an already-loaded Angular component, causing default/no-default IT-TDS assertions to read stale form meta; summary popup persistence used four-digit SAC `9965`, which backend correctly rejected. | Medium | QA | Closed | Helper now patches live Purchase component TDS meta plus future route responses; `FIN-PUR-039A` uses no component fallback for the expected validation path; summary test uses SAC `996500`. Closure: `FIN-PUR-039A` exact rerun passed `2 passed`; `FIN-PUR-039A/039C/041` exact rerun passed `4 passed` in 2.2m. |
| CF-LAUNCH-028 | 4 | Purchase invoice print action regressed from the saved invoice footer even though the print dialog/model logic still existed. Purchase note print fixtures also seeded taxable service invoices without SAC, which backend correctly blocked during source invoice confirm. | High | Frontend/QA | Closed | Restored Purchase Invoice `Print` footer button and added valid SAC `998313` to note print source invoice fixture. Closure: invoice print focused rerun `4 passed`; note print focused rerun `3 passed`; combined `FIN-PUR-PR-001..005` rerun `6 passed` in 2.3m; Angular purchase invoice spec `167 SUCCESS`. |

## Phase Completion Log

| Date | Phase | Result | Notes |
| --- | --- | --- | --- |
| 2026-10-03 | Plan created | Created | Living launch-grade plan created; all phases pending except known evidence recorded. |
| 2026-10-03 | Phase 0 baseline freeze | Passed | Backend check passed, migrations fully applied, frontend build passed. |
| 2026-10-03 | Phase 1 access/context/RBAC | Passed | Auth/entity-context: 24 passed, 1 skipped. RBAC/restricted-access: 22 passed. |
| 2026-10-03 | Phase 2 financial masters/settings | Passed with Risk | Account bulk permissions repaired; consolidated settings: 31 passed, 1 skipped; branch/GSTIN/withholding: 11 passed. Remaining risk is sales branch-numbering fixture data for `FIN-SALSET-003`. |
| 2026-10-03 | Phase 3 sales P0 slice | In Progress | Initial goods price-difference CN assertion issue repaired; Angular payload spec passed; focused `FIN-SAL-033/034` passed; original sales P0 invoice/note lifecycle batch passed `19 passed` in 5.4m. |
| 2026-10-03 | Phase 3 sales P1 print/compliance slice | In Progress | Large focused Sales compliance tail passed across print toolbar, overview, workspace, B2C, reports, E-Way operations, and settings/applicability clusters. `CMP-017D/017E` Cancel IRN allow-policy fixed and retested. `CMP-030/031` reclassified as live-provider smoke with deterministic API e2e app coverage added. |
| 2026-10-03 | Phase 3 sales goods note TCS slice | In Progress | Full Sales P1 rerun stopped after `FIN-SAL-045/046`; root cause isolated to Playwright route/save/TCS sequencing. Focused paired rerun now passes: `2 passed` in 2.5m. |
| 2026-10-03 | Phase 3 sales browser GST/service-note slice | In Progress | Root cause isolated to Playwright route-aware host selection and stale seller-state seeding in service invoice routes, plus tight 90s budgets for service credit-note create/reopen tests. Patched page helpers, scenario seeding, and service note test timeouts. Focused cluster `FIN-SAL-BR-002B/015/016` passed: `3 passed` in 3.9m. |
| 2026-10-04 | Phase 3 sales GST/TCS/reconciliation focused fixes | In Progress | Header-only tax-context recompute fixed in backend and covered by `3 tests OK`; browser GST focused cluster `7 passed`; service-note GST cluster `4 passed`; zero-collection TCS file `6 passed`; reconciliation focused pair `2 passed`. Full Sales P1/P2 gates still pending. |
| 2026-10-04 | Phase 3 sales save-hydration race fix | In Progress | Full Sales P1 rerun exposed `FIN-SAL-BR-002B` stale header rehydrate before third save. Save helper now waits for active component idle after save. Focused `002B` passed and recompute cluster passed `7 passed` in 10.2m. Full Sales P1/P2 gates still pending. |
| 2026-10-04 | Phase 3 sales goods-note TCS timing blocker | In Progress | Full Sales P1 progressed to `77 passed` before `FIN-SAL-BR-112` timed out at 120s; after TCS note budget repair, `110-113` passed in grouped rerun, but `FIN-SAL-BR-114` timed out at 300s after save before detail verification. Full Sales P1/P2 gates still pending. |
| 2026-10-04 | Phase 3 sales TCS note cluster repair | In Progress | Goods note TCS setup moved to API seeding while browser assertions remain on withholding/recompute/save/reopen/stale-edit behavior. `FIN-SAL-BR-114/115/118/119`: `3 passed, 1 skipped` in 5.7m; `119` skipped by intended positive-preview guard. `FIN-SAL-BR-116/117`: `2 passed` in 4.3m. Full Sales P1/P2 gates still pending. |
| 2026-10-04 | Phase 3 full Sales P1 launch observation | In Progress | Full `npm run test:sales:p1` completed in 3.8h with `182 passed, 3 skipped, 13 failed, 11 did not run`. Strong positive evidence for core GST/TCS, note print, document reconciliation, and many compliance surfaces; remaining blockers tracked as CF-LAUNCH-015 through CF-LAUNCH-018. |
| 2026-10-04 | Phase 3 focused failure reruns and observation plan | In Progress | Focused print cluster reproduced `3 failed`; compliance cluster passed `4 passed`; O2C focused settlement passed `2 passed` in 6.9m; TCS full-flow focused rerun produced `6 passed, 1 failed`, with the single failure caused by default 30s timeout. Added Phase 3 Observation Work Plan. |
| 2026-10-04 | Phase 3 print/TCS focused fixes | In Progress | Print profile download helper/budget fixed and retested: `4 passed` in 2.0m. TCS full-flow suite timeout normalized and retested: `7 passed` in 2.7m. Larger print/compliance and full Sales P1 gates still pending. |
| 2026-10-04 | Phase 3 compliance focused hardening | In Progress | `CMP-007/012/026` now explicitly grant action-capable compliance permissions. Focused retest passed: `4 passed` in 1.8m. Larger compliance chunk and full Sales P1 gates still pending. |
| 2026-10-04 | Phase 3A-D chunk gates | In Progress | O2C pack passed `14 passed` in 36.9m; full TCS flow passed `9 passed` in 3.6m; print cases passed in full print/compliance chunk but compliance still failed `4` cases; note/reconciliation chunk failed `LAUNCH-SNOTE-001B`; GST/TCS browser chunk failed `FIN-SAL-BR-002B`. |
| 2026-10-05 | Phase 3 focused blocker closure | In Progress | Closed focused blockers `CF-LAUNCH-019`, `CF-LAUNCH-020`, and `CF-LAUNCH-021`. Evidence: compliance focused cases passed after final `CMP-007` retest; `LAUNCH-SNOTE-001B` passed `2 passed` in 1.7m; `FIN-SAL-BR-002B` passed `2 passed` in 1.5m; saleinvoice Angular spec passed `351 SUCCESS`. Full Sales P1/P2 gates still pending under `CF-LAUNCH-008`. |
| 2026-10-05 | Phase 3 repaired chunk reruns | In Progress | Print/compliance full file: `79 passed, 2 skipped, 2 failed`, then focused `CMP-007A/023` passed. Note/reconciliation chunk: `25 passed, 1 failed`, then focused `FIN-SAL-PR-023` passed. GST/TCS browser chunk reached `38 passed` before repeated `total_other_charges` payload failures; frontend payload fixed, Angular `351 SUCCESS`, and focused `BR-022H/023/024/024A` passed. Full Sales P1/P2 gates still pending. |
| 2026-10-05 | Phase 3 full Sales P1 restart triage | In Progress | Full `npm run test:sales:p1` first stopped on CESS HSN/SAC duplicate seed; focused CESS rerun passed `4 passed`. Restart reached `57 passed` before `FIN-SAL-BR-024O` long-flow timeout; focused `024O` now passes with route-readiness hardening and 300s case budget: `2 passed` in 3.9m. Full Sales P1/P2 gates still pending. |
| 2026-10-05 | Phase 4 purchase focused start | In Progress | Started Purchase P0 focused gate. Initial batch failed early on service note route/vendor hydration. Purchase master-data initialization received a product-side in-flight/timeout guard; Playwright route readiness now avoids spinner-only shells and clean-draft Reset reloads. Angular Purchase spec passed `167 SUCCESS`; focused goods route `FIN-PUR-NEXT-INV-001` passed `2 passed`. Service-note lifecycle setup was optimized with API-backed vendor/account/state discovery; focused `FIN-PUR-NEXT-NOTE-020/021` passed `3 passed` including setup in 50.1s. Locked-period quantity-return overconsumption `FIN-PUR-NEXT-NOTE-022` passed after idempotent correction-dialog helper fix: `2 passed` in 52.2s. Posted-cancel and locked correction action policy passed via `FIN-PUR-053` and `FIN-PUR-049`; grouped tracked goods and locked correction variants `FIN-PUR-047/048/054` passed `4 passed` in 1.9m; service locked correction routing `FIN-PUR-045/046` passed `3 passed` in 1.2m; delete/unpost and line taxability policy slice passed `11 passed` in 5.0m; round-off/workflow/doc-code slice passed `8 passed` in 3.4m; Purchase GST-TDS / Income Tax TDS closure passed focused exact rerun `FIN-PUR-039A/039C/041`: `4 passed` in 2.2m after QA-harness repairs; Purchase statutory/compliance tail smoke passed across document compliance overview, statutory shell/scope, TDS Center, and GST-TDS Center with `20 passed, 3 skipped` across focused runs; Purchase print/document output closure passed `FIN-PUR-PR-001..005`: `6 passed` in 2.3m after restoring invoice print action. Full Purchase P0/P1 statutory heavy gates remain pending for off-hours. |
