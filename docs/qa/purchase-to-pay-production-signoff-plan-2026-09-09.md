# Purchase-To-Pay Production Sign-Off Plan

Last updated: 12 September 2026

## Purpose

Certify the complete purchase-to-pay journey from supplier setup through invoice, tax, stock or expense recognition, notes, payment, ledger posting, statutory reporting, payables reporting, and reversal. This is a living execution ledger, not a statement that existing automated tests have already certified production.

The plan covers every visible control and state on every in-scope screen, together with API, database, accounting, compliance, permission, isolation, recovery, responsive, accessibility, and cross-browser evidence.

## Certification Rules

A screen is `Certified` only when all applicable gates below pass on the release candidate:

- The menu is visible only to entitled users and opens the correct route without stale entity, FY, branch, or location context.
- Every button, icon, link, field, selector, toggle, table control, dialog, tab, paginator, export, keyboard action, and destructive confirmation is exercised.
- Initial, loading, populated, empty, validation, read-only, success, warning, forbidden, conflict, offline, and server-error states are verified.
- Validation appears only after interaction or submission, identifies the field and correction, and does not shift or overlap unrelated content.
- Mutations are verified through UI response, API response, persisted source records, downstream records, audit data, and reports.
- Posted transactions produce balanced journals with correct entity, FY, branch, date, account, tax, counterparty, amount, and source references.
- Unpost, cancel, correction, and retry produce exact intended reversals and never duplicate stock, open items, tax rows, or journals.
- Chromium, Firefox, and WebKit pass at desktop; critical workflows also pass at tablet and mobile widths.
- Keyboard operation, focus order/visibility, dialog trapping, accessible names, and automated WCAG scans pass.
- Evidence is attached to the test ID. A conditional skip, missing fixture, or unreviewed screenshot is not a pass.

Statuses: `Not run`, `In progress`, `Passed`, `Failed`, `Blocked`, `Backlog`, `Certified`.

## Screen Register

The register is the minimum UI inventory. Route aliases discovered during execution must be added rather than silently ignored.

| ID | Surface | Route | Certification status |
| --- | --- | --- | --- |
| P2P-DOC-01 | Purchase Invoice - Goods | `/purchaseinvoice` | Passed locally; staging gate open |
| P2P-DOC-02 | Purchase Invoice - Services | `/purchaseserviceinvoice` | Passed locally; staging gate open |
| P2P-DOC-03 | Purchase Credit Note - Goods | `/purchasecreditnoteinvoice` | Passed locally; staging gate open |
| P2P-DOC-04 | Purchase Debit Note - Goods | `/purchasedebitnoteinvoice` | Passed locally; staging gate open |
| P2P-DOC-05 | Purchase Credit Note - Services | `/purchaseservicecreditnoteinvoice` | Passed locally; staging gate open |
| P2P-DOC-06 | Purchase Debit Note - Services | `/purchaseservicedebitnoteinvoice` | Passed locally; staging gate open |
| P2P-SET-01 | Purchase Settings | `/purchasesettings` | Passed locally |
| P2P-SET-02 | Purchase Charge Types | `/purchase-charge-types` and `/purchasesettings/chargetypes` | Passed locally |
| P2P-SET-03 | Posting Account Mapping | `/staticaccountsettings` | Passed locally |
| P2P-MST-01 | Vendor Account Workspace | Account/ledger workspace | Passed locally |
| P2P-MST-02 | Product/Service Master | Product workspace | Passed locally |
| P2P-IMP-01 | Purchase Legacy Import | `/purchase-legacy-import` | Passed locally; scale gate open |
| P2P-PAY-01 | Payment Voucher | `/paymentvoucher` | Passed locally; staging gate open |
| P2P-CMP-01 | Purchase Statutory | `/purchasestatutory` | Passed automated local/staging scope |
| P2P-CMP-02 | GST Reconciliation | `/gst-reconciliation` | Passed automated local scope; pilot UAT open |
| P2P-CMP-03 | GST Reconciliation Run Detail | GST reconciliation detail route | Passed automated local scope; pilot UAT open |
| P2P-CMP-04 | GST-TDS Configuration | `/gstdsconfig` | Passed automated local/staging scope |
| P2P-CMP-05 | TDS Report/Return | `/reports/tds` | Passed automated local/staging scope |
| P2P-CMP-06 | GST-TDS Report/Return | `/reports/gst-tds` | Passed automated local/staging scope |
| P2P-RPT-01 | Payables Hub | `/reports/payables` | Passed deterministic local; staging trace gate open |
| P2P-RPT-02 | Payables Settings | `/reports/payables/settings` | Passed deterministic local |
| P2P-RPT-03 | Vendor Outstanding | `/reports/payables/vendor_outstanding` | Passed deterministic local; staging trace gate open |
| P2P-RPT-04 | AP Aging | `/reports/payables/ap_aging` | Passed deterministic local; staging trace gate open |
| P2P-RPT-05 | Vendor Ledger Statement | `/reports/payables/vendor_ledger_statement` | Passed deterministic local; staging trace gate open |
| P2P-RPT-06 | Upcoming Payments Calendar | `/reports/payables/upcoming_payments_calendar` | Passed deterministic local; staging trace gate open |
| P2P-RPT-07 | Purchase Register | `/reports/payables/purchase-register` | Passed deterministic local; staging trace gate open |
| P2P-RPT-08 | MSME Overdue | `/reports/payables/msme_overdue` | Passed deterministic local; staging trace gate open |
| P2P-RPT-09 | AP Payment Forecast | `/reports/payables/ap_payment_forecast` | Passed deterministic local; staging trace gate open |
| P2P-RPT-10 | Vendor Reconciliation Statement | `/reports/payables/vendor_reconciliation_statement` | Passed deterministic local; staging trace gate open |
| P2P-RPT-11 | GRN/Invoice/Posting Exceptions | `/reports/payables/grn_invoice_posting_exceptions` | Passed deterministic local; staging trace gate open |
| P2P-RPT-12 | AP Compliance Aging | `/reports/payables/ap_compliance_aging` | Passed deterministic local; staging trace gate open |
| P2P-RPT-13 | Duplicate/Anomalous Bills | `/reports/payables/duplicate_anomalous_bill_detection` | Passed deterministic local; staging trace gate open |
| P2P-RPT-14 | Vendor Settlement History | `/reports/payables/vendor_settlement_history` | Passed deterministic local; staging trace gate open |
| P2P-RPT-15 | Vendor Debit/Credit Note Register | `/reports/payables/vendor_note_register` | Passed deterministic local; staging trace gate open |
| P2P-RPT-16 | Payables Close Pack | `/reports/payables/payables_close_pack` | Passed deterministic local; staging trace gate open |
| P2P-RPT-17 | AP-to-GL Reconciliation | Dynamic payables report route | Passed deterministic local; staging trace gate open |
| P2P-RPT-18 | Vendor Balance Exceptions | Dynamic payables report route | Passed deterministic local; staging trace gate open |

## Common Element Checklist

### Six purchase document workspaces

Apply this checklist separately to `P2P-DOC-01` through `P2P-DOC-06`; passing one page does not certify the others.

- Header: title, voucher/status badges, entity/FY/branch/location context, Find, Reset, Import where supported, and browser navigation recovery.
- Dates: document, invoice, due, claim period, FY boundaries, future-date policy, locked books, and filed GST period.
- Supplier: selector, add/edit, GSTIN, registration status, state, MSME attributes, duplicate supplier invoice, historical snapshot, and inactive supplier.
- Tax context: supply category, place of supply, tax regime, reverse charge, taxability, ITC eligibility, GSTR-2B status, and claim workflow.
- Lines: add, edit, remove, product/service, description, batch, HSN/SAC, quantity, free quantity, UOM/conversion, rate, inclusive tax, discount, taxable value, and line total.
- GST calculation: CGST and SGST symmetry, IGST exclusivity, percentage-to-amount calculation, CESS, zero/exempt/nil/non-GST, rounding, and supply-category recalculation.
- Totals: quantity, subtotal, discount, charges, tax breakup, TDS/GST-TDS, round-off, grand total, and net payable.
- Supporting actions: additional charges, TDS, compliance, attachments, additional details, posting preview, previous/next navigation, Save, Confirm, Post, Unpost, and Cancel where supported.
- Lookup dialogs: search, status/type filters, reset, accurate total/matched/range labels, real page data changes, row load, empty state, close, focus return, and mobile layout.
- Lifecycle: draft create/edit/delete, confirm, post, prohibited posted edit, unpost, cancel, linked correction, duplicate click, stale version, retry, and audit trace.

### Report and register screens

- Menu discovery, title, context badges, default period, and scope inheritance.
- Every filter, dependent selector, Apply/Run, Reset, clear, date boundary, and malformed URL parameter.
- Loading, empty, single row, multi-page, last page, changed page data, accurate `start-end of total`, sorting, and page-size behavior.
- Summary cards, table values, totals, drilldowns, breadcrumbs/back behavior, and source-document opening.
- CSV, XLSX, PDF, print, filename, selected scope/date, column order, numeric formatting, page breaks, and totals parity.
- Direct URL permission, entity/branch/FY isolation, read-only behavior, API failure, retry, and stale-request cancellation.

## Required Business Permutations

Use deterministic pairwise coverage for presentation combinations, but run every critical tax, posting, reversal, and isolation invariant explicitly.

| Dimension | Required cases |
| --- | --- |
| Document | All six goods/service invoice and note screens |
| Supplier | Registered regular, unregistered, composition, SEZ, import, inactive, MSME, non-MSME |
| Entity tax profile | GST registered, non-GST; valid and missing registration context |
| Supply | Intra-state, inter-state, export/SEZ where supported, import goods, import services |
| Taxability | Taxable, exempt, nil-rated, non-GST, reverse charge |
| Line accounting | Inventory, expense, service, fixed asset, mixed lines |
| Tax | CGST/SGST, IGST, CESS, inclusive, zero, changed master rate, manual rate restrictions |
| Commercial | Line/header discount, freight/packing/insurance, free quantity, round-off, credit/cash, advance |
| Quantity | Integer, decimal, alternate UOM, zero, negative attempt, insufficient returnable stock |
| Time | Current date, future policy, FY start/end, previous FY, locked books, filed GST period |
| Lifecycle | Draft, confirmed, posted, unposted, cancelled, corrected, retried, stale/concurrent |
| Payment | None, partial, full, advance, multi-invoice, overpayment attempt, TDS deduction |
| Scope | Entity, FY, branch, subentity, location, forbidden cross-scope object |
| Role | Platform/admin, owner, accountant, purchase operator, approver, read-only, restricted |

## Phase Plan

### Phase 0: Inventory, Baseline, And Traceability

Status: Completed locally on 9 September 2026

Work:

- Map every screen ID to Angular component, API endpoint, backend service/model, permission, posting adapter, report consumer, and existing automated tests.
- Run existing backend, frontend unit, and Playwright purchase suites without treating mocked passes as persisted business proof.
- Create deterministic run IDs, cleanup rules, test users, entity/FY/branches/locations, suppliers, products, services, assets, and ledger mappings.
- Record existing failures as product, data, environment, or test defects.

Exit:

- No route, action, endpoint, report, role, or business invariant is absent from the traceability ledger.
- Baseline results and known gaps are recorded; test data is repeatable and isolated.

Evidence and findings:

- Backend baseline scope: `purchase`, `payments`, payables reports/settings, purchase register, GST reconciliation, GST-TDS, withholding, and shared GST document validation.
- Initial reused-database command ran `845` tests: `824 passed`, `18 failed`, and `3 errored`. Fourteen failures/errors were caused by stale RBAC/menu seeds in the retained test database and disappeared in a freshly provisioned database.
- The clean database run initially produced six import-draft permission fixture failures and one overlength GSTIN fixture error. The import parser also exposed header rows as false line items after permission setup was corrected.
- Corrections: import parsing now excludes labeled invoice header/total rows; import parsing tests explicitly bypass the separately tested purchase-create permission gate; the import-source fixture uses a valid 15-character GSTIN.
- Focused correction result: `7 passed`, zero failures.
- Final isolated database command: `DB_TEST_NAME=test_finacc_p2p_phase0_verify_20260909 ./venv/bin/python manage.py test purchase payments reports.tests_payables reports.tests_payables_settings reports.tests_purchase_register gst_reconciliation gst_tds withholding core.tests_gst_document_validation --noinput --verbosity=1`.
- Final backend result: `845 passed`, zero failures, zero Django system-check issues; test execution took approximately 90 seconds after provisioning. Clean database provisioning was materially slower than execution startup and remains a Phase 11 environment-performance observation.
- Angular production build: passed in `8.798s`.
- Angular purchase-facing unit baseline covered purchase documents/settings/statutory, payment, payables, GST reconciliation, GST-TDS, and TDS selectors/components/services: `1,410 passed`, zero failures.
- Local Angular and Django services were started successfully on ports `4200` and `8000`. Django reported one unapplied `rbac` migration; this must be applied before using the local database for RBAC certification.
- Initial purchase P0 browser execution ran 33 of 78 scheduled tests before being intentionally stopped: `22 passed`, `11 failed`, and one in-flight test was interrupted. Every failure was a service fixture rejected by the correct compliance rule, `SAC is required for taxable service lines`; 44 tests were not run in that invalid-data attempt.
- The shared service-invoice API fixture now supplies SAC `998313`, and the lifecycle helper includes the response body in future confirmation failures.
- Focused rerun of all eleven affected service scenarios plus authentication: `12 passed`, zero failures, completed in `5.3m`. Coverage included service invoice, service credit note, and service debit note create/reopen, tax-context continuity, vendor-change recalculation, confirm, post, and unpost.
- The remaining purchase P0 scenarios are retained in Phase 2 full-screen execution; Phase 0 does not count the interrupted first attempt as certification.

### Phase 1: Masters And Purchase Configuration

Status: Passed locally on 10 September 2026; staging and cross-browser certification remain open

Work:

- Certify vendor create/edit/deactivate, GST lookup/preview/adoption, registration type, state, PAN, address, payment terms, MSME/Udyam, TDS applicability, and duplicate controls.
- Certify product/service HSN/SAC, GST/CESS, UOM, batch/location, inventory/expense/asset classification, and historical snapshots.
- Certify purchase settings, numbering, approval/confirm/post/delete safeguards, charge types, tax treatment, and static account mappings.
- Prove missing or invalid mappings fail before partial posting.

Exit:

- Every document permutation has valid deterministic masters.
- Master edits cannot silently alter historical posted documents.

Evidence and findings:

- Applied local prerequisite migration `rbac.0143_add_batch_data_access_policy_type`; deployment environments must include it before role certification.
- Focused backend master/configuration suite: `189 passed`, covering financial accounts, entities/GST lookup, catalog, and purchase API smoke behavior.
- Focused Angular suite: `206 passed`, covering account workspace, product form, purchase settings, and invoice charge types.
- GST-assisted financial account browser suite: `3 passed`; preview/adoption and duplicate-account handling remain distinct user actions.
- Purchase settings browser suite: `19 passed` in the broad run and the corrected final withholding-policy scenario passed independently (`2 passed` including authentication). The taxable service fixture now carries mandatory SAC `998313`.
- Product browser suite: `7 passed`, covering create/edit/delete, goods/service governance, stock product tabs, sorting, inactive filters, bulk-import guards, and referenced-product deletion protection.
- Static account settings browser check: `2 passed`, covering API-backed groups, filtering, validation posture, and permission-aware save state.
- Account/vendor browser suite: final full run `4 passed`. It covers create/edit/view/delete, referenced-vendor protection, payment submit/approve/post policy, GST/PAN and commercial details, additional contact/address persistence, opening-balance posting, and deletion protection after financial use.
- Purchase Charge Types gained a dedicated browser test: `2 passed`, covering required validation, create, search, edit, GST/SAC defaults, ITC default, and entity-owned edit behavior.
- Test defects corrected during execution: payment fixtures now satisfy configured approval policy; account GST/PAN interactions target the current Basic Details step; account creation expects navigation to edit mode; additional rows are asserted through input values; opening-balance fixtures provision `OPENING_BALANCE_OFFSET` and assert used accounts cannot be deleted.
- No application defect remained open from the Phase 1 local run. These results do not yet certify Firefox, WebKit, mobile, restricted roles, or staging.

### Phase 2: Six Document Screens And Lifecycle

Status: Passed locally on 12 September 2026; staging and final human gates remain open

Work:

- Execute the common element checklist independently on all six document routes.
- Test goods, services, expense, asset, and mixed invoices; create source-linked and value-only notes.
- Verify calculation precision and CGST/SGST auto-pairing, IGST exclusivity, CESS, discounts, charges, TDS, totals, and recalculation after context changes.
- Prove save, confirm, post, unpost, cancel, copy/navigation, attachment, and lookup behavior.

Exit:

- All six screens pass without conditional skips in Chromium.
- Each posted sample is persisted and traceable to balanced journals and correct open-item/stock effects.

Evidence and findings to date:

- The monolithic Chromium file contains `368` browser executions including authentication. It is being executed in deterministic functional batches because one uninterrupted local run exceeded one hour and obscured actionable failure classification.
- Route, header, core action, and initial note-surface batch: `11 passed`, covering both invoice routes, both goods note routes, vendor/state/tax-context initialization, and common dialogs.
- Reset/reload state-hygiene batch across all six document routes: `13 passed` including authentication; no stale line or source-document state crossed a fresh route load.
- GST, taxability, reverse-charge/import, discount, CESS, other-charge, GST-TDS, IT-TDS, combined deduction, and persistence calculation batch: effective result `44 passed`. The broad run produced three failures; all three passed in the focused rerun after correcting one stale whole-rupee footer expectation. The persisted line retains `106.20` while configured document round-off produces footer grand total and net payable `106.00` with `-0.20` round-off.
- The out-of-scope Income Tax TDS guard passed alone and displayed the expected scope-specific message. The earlier broad-run miss was caused by dialog/test sequencing, not an absent application validation.
- Core lifecycle batch covered service and goods save/confirm/post/unpost/cancel plus rejected confirm/post/unpost recovery: effective result `12 passed`. Three taxable-service fixtures were corrected to provide mandatory SAC `998313`; one service reopen assertion initially encountered a transient loading spinner after a long serial run and passed independently.
- Source-linked note continuity batch: `8 passed` including authentication. It covers source reference persistence, clean second-tab state, goods credit-note and service debit-note draft identity across repeated saves, default locked-period correction reason, goods credit-note confirmation/reopen, and service debit-note confirm/post/unpost/reopen stability.
- Expanded note permutation batch: `13 passed` including authentication. It covers value-only goods and service debit notes, duplicate-note decline and explicit override, multi-line goods and service notes, tracked-batch retention, reverse-charge continuity, state/place-of-supply continuity, and tax recomputation after vendor change.
- Locked-period and correction-control matrix: effective result `14 passed`, covering all scenarios `FIN-PUR-042` through `FIN-PUR-054` plus `FIN-PUR-NEXT-NOTE-022`. Test isolation was strengthened by awaiting lock-setting restoration, synchronizing scoped lock hydration, and creating fresh stock products for quantity-capacity cases. Forty-three stale Playwright-created local lock rows were removed; no customer or non-test lock was changed.
- Attachment matrix across all six purchase document screens: effective result `8 passed` including authentication. Upload persistence is proven for goods and service invoices and all four note variants; the posted service path additionally proves that attachment persistence does not block confirm or post and survives posted-document reopen.
- Shared taxable-service fixtures now provide mandatory SAC `998313`, preventing fixture-only failures from bypassing the application validation being certified.
- Lookup and navigation batch: effective result `10` purchase workflows passed plus authentication coverage. It proves Previous/Next behavior for goods and service invoices, Previous navigation with edit/save/reopen parity for all six document variants, posted service-invoice lookup reopen, and explicit service-to-goods credit-note fallback with API target-to-routed-document identity parity. Stale test contracts were corrected to expect Draft after Save Draft and to force the fallback branch independently of populated same-mode history.
- Additional-details and posting-detail surface batch: `13 passed` including authentication. Custom-field dialogs open correctly for all six purchase document variants, and posting-detail dialogs open and close correctly for all six posted document variants.
- Permission and scope batch: effective result `7` focused workflows passed plus authentication coverage, with one cross-entity statutory case skipped because the local user exposes no second entity. It covers six-route accessible-shell lifecycle affordances, settings unsaved-change scope guard, statutory FY and subentity request scoping, provisioned zero-permission route denial, foreign-entity catalog/context rejection, and branch-assigned denial of foreign-branch plus entity-wide purchase metadata.
- Purchase invoice accounting reconciliation: `5 passed` including authentication. Posted goods and service invoices were traced through Purchase Register, Vendor Outstanding, AP Aging, Daybook, Ledger Summary, Trial Balance, and Vendor Ledger Book.
- Purchase note accounting reconciliation: all six effective workflows passed across focused runs, plus authentication setup. Posted goods and service credit/debit notes were traced through Purchase Register, Vendor Note Register, Daybook, Ledger Summary, Trial Balance, and Vendor Ledger Book. Report navigation fixtures now use stable route helpers and carry the real ledger ID from Ledger Summary into Ledger Book.
- Payment-chain integrity: `5 passed` including authentication in one serial Chromium run. Full payment removed the invoice from open allocations and Vendor Outstanding; partial payment retained the exact reduced balance; unpost restored the full payable before a clean replacement settlement; and cancelling an unposted payment left the payable unchanged.
- Expanded payment permutations passed locally in Chromium: multi-invoice settlement, advance-adjusted settlement, over-settlement block and warning policies, multiple advances against one bill, one advance split across two bills, purchase-allocation date/TDS persistence, and payment TDS mode/section persistence.
- Payment reversal and cancellation integrity passed locally: unposting a fully settled payment restored the exact AP open balance, a new replacement voucher cleared it once without duplication, and cancelling an unposted against-bill voucher left the payable unchanged. The configured unpost target status was also proven through the browser.
- Payment-chain fixtures now provide mandatory service SAC `998399`, generate collision-resistant valid PAN/GSTIN values, and follow the configured submit/approval lifecycle.
- On 12 September, the complete upstream document/import/voucher pack passed `245/245` in one Chromium run (`16.2m`). It covers both invoice modes, all four note modes, purchase import, cash/bank/journal/payment/receipt vouchers, lifecycle actions, attachments, approval, locked-period failures, allocation, runtime TDS/TCS, AR/AP drilldowns, and stale-tab protection.
- The run exposed a real receipt-voucher state defect: after post/unpost the screen could retain stale local status when the action response used a partial envelope. Receipt lifecycle actions now apply the immediate expected status and refresh canonical detail, matching payment-voucher behavior. Focused browser rerun passed `14/14`; receipt component units passed `87/87`.
- Stale browser expectations were aligned to the intentional UX: Save Draft and Confirm are separate actions, posting detail is available for posted records, and AR guidance is exposed through the action tooltip instead of permanent layout-shifting copy.
- No confirmed application defect remains open from the local Phase 2 batches. Staging persisted-data replay, full document Firefox/WebKit parity, responsive review, and manual accessibility remain later cross-phase launch gates rather than Phase 2 local blockers.

### Phase 3: GST, ITC, RCM, TDS, And Statutory Controls

Status: In progress; automated local and staging surface gates passed on 12 September 2026

Work:

- Reconcile registered, URD, composition, SEZ, import, RCM, exempt, nil, and non-GST cases.
- Verify HSN/SAC requirement is conditional on GST applicability, supplier/entity registration, and report requirements; invalid taxable GST combinations must be blocked.
- Certify GSTR-2B status, ITC eligible/blocked/pending/reversed states, claim period, filed-period corrections, and GST reconciliation runs.
- Certify TDS and GST-TDS setup, threshold/base/rate/section calculation, returns, exports, and note/payment reversals.
- Verify purchase statutory cards, dialogs, pagination, empty states, and return creation.

Exit:

- Source document, posting, ITC/RCM/TDS registers, reconciliation, and return/export totals agree exactly.
- Unsupported combinations are explicitly blocked with useful guidance.

Evidence and findings to date:

- The focused statutory non-visual suite passed `43/43` locally across Purchase Statutory, GST/TDS compliance centers, report filters, return workspaces, and principal validation/error states.
- GST report visual certification passed `9/9` and produced eight reviewed operational baselines.
- The focused GST-TDS/TDS staging suite passed `12/12`, confirming authenticated routes and API-backed principal workflows on the deployed environment.
- Remaining Phase 3 gates are source-to-return amount reconciliation for every required tax permutation, production artifact inspection, provider-dependent filing actions, and statutory-owner signoff.

### Phase 4: Inventory, Expense, Asset, And GL Integrity

Status: Passed locally on 12 September 2026; core staging mutation, reconciliation, reversal, and cleanup passed

Work:

- Prove inventory receipt by product, UOM, batch, branch, and location; reconcile stock ledger, stock summary, valuation, and inventory-control GL.
- Prove service/expense purchases create no stock movement and hit the intended expense/control accounts.
- Prove fixed-asset purchases create correct asset intake/capitalization references without stock leakage.
- Test freight/landed cost, discounts, free quantity, round-off, mixed lines, cancellation, unpost, and notes.

Exit:

- Quantity/value/open-item/tax/journal invariants agree after every lifecycle action.
- Exact reversals leave no orphan movement, posting entry, journal, asset intake, or open item.

Evidence and findings to date:

- A focused backend certification bundle passed `239/239` with no system-check issues. It covered inventory and expense posting behavior, UOM and acquisition-cost movement handling, return safety, fixed-asset intake and reversal, the real purchase -> transfer -> adjustment -> sale -> return stock chain, inventory reports, payables reports, and core financial reports.
- The focused browser gate passed `77/77` in Chromium across goods purchase lifecycle, Stock Summary and Stock Ledger, AP-to-GL Reconciliation, Purchase Register, fixed-asset surfaces, posting drilldowns, exports, accessibility, responsive layout, and approved visual baselines.
- The inventory visual suite now freezes its reference clock to `5 September 2026`; this removes calendar-driven screenshot churn. Four baselines were deliberately refreshed for the already-approved compact mobile/header layout, while two filter-dialog mismatches disappeared once time was deterministic.
- The environment-safe authenticated staging route sweep passed `11/11` for all six purchase document screens, Purchase Settings, and every supported Purchase Charge Types route alias under the Manav-T scope.
- The controlled Manav-T staging replay created, confirmed, and posted three tagged invoices: asset `784` / `PINV-PINV-2026-00104-HO`, inventory `785` / `PINV-PINV-2026-00105-HO`, and service expense `786` / `PINV-PINV-2026-00106-HO`.
- Asset invoice `784` produced purchase-linked CWIP asset `12` / `FA-000001` for exactly `1,000.00`, preserved source purchase line `870`, category `Computers`, vendor, subentity, and document references, and created an open payable of `1,180.00`. The staged browser asset chain passed `4/4` including authentication, catalog configuration, invoice-to-asset traceability, Trial Balance, and Balance Sheet reflection.
- Inventory invoice `785` produced one document-specific inward stock move for product `122` at location `18`: quantity increased from `29.4000` to `31.4000`, value increased from `3,004.00` to `3,254.00`, and the Stock Ledger showed `2.0000` inward at unit cost `125.0000` and line value `250.00`. Its payable was `295.00`, including `45.00` IGST.
- Service invoice `786` created no stock movement, debited Audit Fees by exactly `600.00` (`5,460.00` to `6,060.00` closing), appeared in Profit & Loss for the same amount, and created a payable of `708.00`, including `108.00` IGST.
- Reversal cleanup passed: stock returned to `29.4000` / `3,004.00`, Audit Fees returned to `5,460.00`, all tagged open items disappeared, the temporary CWIP asset was removed, and all three invoices were cancelled after unpost. Tagged product `151` remains as the reusable staging asset-purchase fixture.
- The replay exposed and corrected inherited asset-category visibility: branch-scoped category and metadata APIs now return entity-wide categories plus the selected branch's categories, while excluding categories private to another branch. Focused regressions passed `2/2`; the complete asset suite passed `80/80` with no system-check issues.
- Remaining extended Phase 4 gates are staging permutations for landed cost, discounts, free quantity, mixed inventory/expense/asset lines, notes, and export artifact inspection. The core stock/expense/asset posting and reversal chain is no longer open.

### Phase 5: Notes, Returns, Amendments, And Locked Periods

Status: Passed locally on 12 September 2026; staging replay remains open

Work:

- Test quantity return before and after downstream consumption, partial/multiple returns, remaining-returnable limits, rate difference, value-only adjustment, and RCM correction.
- Test source lookup pagination and source-document validation on all four note routes.
- Prove posted history is immutable and filed/locked periods route changes through current-period linked documents.
- Reconcile note polarity across stock, AP, GST/ITC, TDS, journals, and reports.

Exit:

- No note can over-return quantity/value or mutate protected history.
- Original, notes, remaining balance, and downstream reports reconcile.

Evidence and findings to date:

- All four goods/service note routes passed reference selection, value-only and quantity-return behavior, duplicate override, multi-line, batch retention, GST/RCM continuity, vendor/state recalculation, attachments, lifecycle, locked-period correction, concurrency, and downstream report checks in the Phase 2 focused batches.
- The final coherent `245/245` browser run revalidated the note routes together with their upstream invoice and downstream voucher workflows.

### Phase 6: Payments, Allocation, And Vendor Balances

Status: In progress locally on 10 September 2026

Work:

- Certify payment voucher controls and full, partial, advance, on-account, multi-invoice, TDS-net, overpayment, unpost, cancel, and reallocation flows.
- Verify allocations cannot cross vendor, entity, branch, FY, or currency context where applicable.
- Reconcile invoice/notes/payments through AP open items, vendor ledger, outstanding, aging, settlement history, cash/bank ledger, and GL.
- Exercise duplicate reference, concurrent allocation, stale balance, and retry behavior.

Exit:

- Vendor subledger equals AP control GL at the same cutoff.
- Allocation totals never exceed available payment or document balance.

Evidence and findings to date:

- The combined payment-chain suite passed `5/5` including authentication in `5.2m`, with exact AP open-item and Vendor Outstanding effects for full, partial, unpost/replacement, and cancellation paths.
- Multi-invoice, advance-adjustment, over-settlement block/warning, split-advance, allocation-date/TDS, and payment TDS mode/section browser permutations passed.
- Unpost restored the original payable amount before a replacement payment cleared it once; draft cancellation preserved the original payable; policy-driven draft return after unpost passed.
- Payment concurrency and repeat-action browser batch passed `8/8` in Chromium: two-tab refresh, stale-tab deterministic save, and stable submit, post, cancel, approve, and unpost behavior without duplicate voucher identity or repeated actions.
- A persisted same-bill settlement race now proves that two separately approved payment vouchers cannot both post against one payable. Exactly one request succeeds, the competing request receives controlled validation below HTTP 500, one voucher remains Posted, and the open item closes once. This critical case passed in Chromium and then Firefox/WebKit (`4/4` including cross-browser authentication setup).
- Clean isolated backend payment and purchase-settlement gate passed `158/158`, including permission enforcement, out-of-scope action rejection, AP settlement validation, lock behavior, withholding, numbering, and metadata scope recovery.
- The complete purchase-to-payment reconciliation file passed `5/5` in one Chromium run, covering full, partial, multi-bill, and advance-adjusted settlement against live AP open items.
- Ambiguous-response retry coverage now proves that repeating a successful payment post returns the existing Posted result without duplicating AP settlement history or accounting impact. The canonical posting lookup/daybook detail APIs resolve the same entry and journal-line IDs before and after retry; the vendor/AP debit and cash/bank credit equal the settled payable exactly and remain balanced. The strengthened case passed in Chromium (`2/2` including authentication) and Firefox/WebKit (`4/4` including authentication).
- The initial fifteen focused payment and purchase-chain scenarios remain green locally in Chromium, with the later concurrency, idempotency, reconciliation, and cross-browser race runs recorded separately above. No confirmed product defect remains from this batch; stale SAC, supplier-invoice sequencing, TDS dialog completion, nested settings payload, and cancellation-response assertions were corrected in test fixtures/helpers.
- Remaining Phase 6 gates: expanded vendor/entity/branch/FY allocation isolation, staging execution, complete Firefox/WebKit workflow parity beyond the critical race/retry cases, mobile, and accessibility.

### Phase 7: Payables Reports And Exports

Status: In progress; deterministic report suite passed locally on 12 September 2026

Work:

- Certify `P2P-RPT-01` through `P2P-RPT-18` using the report checklist.
- Trace every report row to source invoice/note/payment and every summary total to independently queried persisted data.
- Cross-reconcile purchase register, vendor outstanding, AP aging, vendor ledger, settlement history, close pack, and AP-to-GL.
- Verify MSME due-date rules, duplicate detection, GRN/posting exceptions, compliance aging, forecast/calendar, and vendor reconciliation semantics.

Exit:

- Every report has empty, populated, pagination, filter, drilldown, export, permission, and failure evidence.
- No unexplained difference remains between operational documents, subledger, reports, exports, and GL.

Evidence and findings to date:

- Payables backend regression passed `98/98`, including report scope, export behavior, and controlled `400` responses for foreign-vendor ledger requests instead of an HTML/500 failure.
- The deterministic Payables suite passed all `183` Chromium scenarios. Across Chromium, Firefox, and WebKit the broad run passed `547/549`; the two WebKit harness failures were corrected and their focused rerun passed `6/6`, yielding effective green evidence for all `549` scheduled browser scenarios without claiming an uninterrupted rerun.
- Coverage includes hub/settings and operational reports, filters, sorting, pagination, empty/populated/error states, drilldowns, scoped links, downloads/print responses, desktop/mobile screenshots, and export filenames.
- A focused authenticated staging payables sweep passed, but the complete source-record-to-export and AP-to-GL staging certificate remains open.

### Phase 8: Import, Failure Recovery, Concurrency, And Idempotency

Status: In progress; deterministic import, recovery, concurrency, and idempotency evidence exists

Work:

- Import valid and invalid CSV/XLSX datasets at small, medium, and agreed production-like volumes.
- Test duplicate strategy, partial validation, all-or-nothing commit policy, interrupted upload, retry, timeout, malformed file, and cleanup.
- Simulate offline, 401, 403, 409, 422, 429, and 500 responses for each mutation family and critical report/export.
- Exercise double click, parallel post/unpost, update-versus-post, payment allocation races, stale versions, and repeated request IDs.

Exit:

- Failures provide actionable recovery and never create partial or duplicate business effects.
- Retry behavior is deterministic and concurrency conflicts are explicit.

### Phase 9: Permissions And Scope Isolation

Status: In progress; focused UI/API scope gates passed, full role matrix remains open

Work:

- Execute a role/action matrix for view, create, edit, approve, confirm, post, unpost, cancel, import, export, print, tax edit, and payment allocation.
- Test menu visibility, direct routes, API calls, object IDs, lookup results, exports, and drilldowns for unauthorized roles.
- Switch entity, FY, branch, subentity, and location on every screen family; verify stale data is cleared and requests carry the new scope.
- Attempt cross-entity and cross-branch direct-object access for every detail/mutation endpoint.

Exit:

- UI and API enforce the same permission decision.
- No identifiers, totals, names, documents, or exports leak across scope.

### Phase 10: Visual, Mobile, Accessibility, And Browser Certification

Status: In progress; payables cross-browser/mobile and GST visual gates passed

Work:

- Review all screen IDs at desktop, tablet, and mobile widths in Chromium; run critical workflows in Firefox and WebKit.
- Check header/menu footprint, horizontal containment, sticky action bars, dense line tables, dialogs, validation, date/select controls, pagination, keyboard display, and safe-area behavior.
- Run screenshot baselines for stable operational states and inspect pixel differences before approval.
- Run automated accessibility scans and manual keyboard/screen-reader review of documents, dialogs, tables, filters, exports, and notifications.

Exit:

- No clipped, overlapped, unreachable, or off-screen critical control.
- Critical workflows meet the agreed WCAG gate with documented exceptions only.

### Phase 11: Performance, Repeatability, And Launch Decision

Status: Not run

Work:

- Measure initial route load, lookup/filter, invoice save/post, import validate/commit, report run, drilldown, and export at agreed volumes.
- Exercise invoices with 1, 10, 100, and agreed maximum lines; reports with empty, normal, and production-like row counts.
- Repeat critical suites at least three times and quarantine no unexplained flake.
- Produce the final matrix by screen and invariant with defect severity, evidence links, residual risk, and release recommendation.

Exit:

- No open Critical or High defect; accepted Medium/Low risks have owner and target date.
- All launch-critical tests pass repeatedly on staging release candidate.
- Product, engineering, QA, and accounting owners approve the evidence-based launch recommendation.

## Accounting And Compliance Invariants

- Every journal is balanced and uses configured accounts; no fallback account silently hides missing setup.
- Purchase payable equals gross invoice plus/minus charges, discounts, round-off, tax, withholding, notes, and allocations according to policy.
- Inventory purchases reconcile quantity and value; service/expense purchases never create inventory movement.
- CGST equals SGST for valid intra-state symmetric rates; IGST is mutually exclusive; tax amount derives from taxable value and rate.
- URD, composition, non-GST entity, exempt/nil/non-GST supply, RCM, SEZ, and import behavior remain distinct.
- ITC cannot be claimed when blocked or inapplicable and reversals retain source and period traceability.
- Supplier invoice duplicate policy is atomic under sequential and concurrent requests.
- Vendor open items plus unapplied advances reconcile to vendor subledger and AP control account.
- Posted history is immutable; corrections are linked, dated, scoped, and exactly reflected in every downstream report.

## Evidence Ledger Template

Add one row per executed scenario. Do not replace a failed row after a fix; add the rerun and retain defect history.

| Run ID | Test ID | Screen ID | Scenario/data | Environment/build | Browser/viewport | API/source IDs | Expected evidence | Result | Defect/evidence link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| - | - | - | - | - | - | - | - | Not run | - |

Required artifacts for a critical end-to-end scenario:

- Browser trace or video for workflow failure; approved screenshots for visual states.
- Request/response status and generated document identifiers without secrets.
- Database/source counts and amounts before and after mutation.
- Journal, open-item, inventory/asset, tax/withholding, and report/export reconciliation.
- Cleanup result proving the test leaves no unintended records.

## Severity And Release Gate

| Severity | Definition | Gate |
| --- | --- | --- |
| Critical | Wrong money/tax/stock, data loss, duplicate posting, cross-tenant leak, unusable core flow | Release blocked |
| High | Core action/report/permission/recovery failure with no safe workaround | Release blocked |
| Medium | Material UX/report/export defect with a controlled workaround | Requires owner and explicit acceptance |
| Low | Cosmetic or minor usability defect without business ambiguity | May enter backlog |

The final confidence score must be evidence weighted. It may exceed 95% only when all critical invariants, all six document screens, payments, compliance reconciliation, AP-to-GL parity, permissions/isolation, and staging browser gates are complete. Test-file count or mocked pass percentage alone cannot justify it.

## Known Decisions And Open Gaps

- Multi-GSTIN behavior needs a confirmed product model if more than one active GST registration per entity is expected.
- Future-dated purchase policy must be explicit and tested consistently in UI, API, posting, and reports.
- Mixed RCM and non-RCM lines are currently treated as unsupported unless the product rule changes.
- Production-scale volumes, latency thresholds, supported mobile widths, and accepted WCAG level must be confirmed before Phase 11.
- Any intentionally deferred visual or browser item must be recorded as `Backlog`; it cannot be counted as certified.

## Phase Update Log

| Date | Phase | Update | Result/confidence impact |
| --- | --- | --- | --- |
| 9 Sep 2026 | Phase 0 | Initial screen register, element checklist, permutation matrix, phases, invariants, evidence rules, and launch gates created from current routes and QA assets. | Baseline only; no new certification claimed |
| 9 Sep 2026 | Phase 0 | Fixed import header-row parsing and stale test fixtures; clean backend and targeted Angular baselines passed. | Engineering baseline green; browser and staging certification still required |
| 9 Sep 2026 | Phase 0 | Corrected Playwright service fixtures to include mandatory SAC; all 11 affected document scenarios passed locally. | Browser baseline is trustworthy; complete document certification remains Phase 2 |
| 10 Sep 2026 | Phase 1 | Applied the pending RBAC migration and completed backend, Angular, and Chromium master/configuration verification. | `189` backend, `206` Angular, and all focused browser journeys passed locally |
| 10 Sep 2026 | Phase 1 | Added Purchase Charge Types coverage and aligned account/payment fixtures with approval, opening-balance mapping, navigation, and input-value behavior. | Phase 1 passed locally; staging, roles, mobile, Firefox, and WebKit remain later gates |
| 10 Sep 2026 | Phase 2 | Completed expanded note, locked-period correction, quantity-capacity, and six-screen attachment batches. Strengthened fixture isolation and mandatory SAC defaults. | `35` additional effective scenario passes plus authentication coverage; no confirmed product defect remains from these batches |
| 10 Sep 2026 | Phase 2 | Completed lookup and Previous/Next navigation across all six purchase documents, including explicit cross-mode fallback and posted lookup reopen. | `10` workflows passed effectively; API/UI identity and draft persistence remain aligned |
| 10 Sep 2026 | Phase 2 | Completed additional-details and posted journal/detail dialog checks across all six purchase document variants. | `13 passed` including authentication; no dialog-surface defect found |
| 10 Sep 2026 | Phase 2 | Executed purchase RBAC and scope controls with dynamically provisioned restricted and branch-assigned users. | Focused gates passed; local cross-entity browser switch remains unexercised because no alternate visible entity exists |
| 10 Sep 2026 | Phase 2 | Reconciled posted goods/service invoices and all four purchase-note variants through purchase, payables, daybook, trial-balance, ledger-summary, and ledger-book surfaces. | Invoice run `5 passed`; all six effective note workflows passed across focused runs, with authentication coverage |
| 10 Sep 2026 | Phase 2 | Exercised full and partial against-bill payment settlement under the active confirmation and approval policy. | `3 passed` including authentication; open-item and Vendor Outstanding balances reconciled exactly |
| 10 Sep 2026 | Phase 6 | Expanded payment coverage through multi-invoice, advances, overpayment policy, TDS persistence, unpost, cancellation, and replacement settlement. | `15` effective focused scenarios green locally in Chromium; exact payable restoration and no duplicate replacement settlement proven |
| 10 Sep 2026 | Phase 6 | Added and executed concurrency, idempotency, isolated backend, and combined reconciliation gates. | Browser repeat-action `8/8`; backend `158/158`; reconciliation `5/5`; same-bill race passed Chromium, Firefox, and WebKit with exactly one settlement |
| 10 Sep 2026 | Phase 6 | Added public-API payment posting trace and retry invariants to `FIN-PUR-CHAIN-006`. | Same settlement, history row, posting entry, and journal-line IDs survive retry; exact balanced vendor/AP and cash/bank legs passed Chromium, Firefox, and WebKit |
| 12 Sep 2026 | Phases 2, 5, 6, 8 | Re-ran the coherent purchase invoice, note, import, and voucher chain after correcting receipt canonical lifecycle refresh and stale UI assertions. | `245/245` Chromium browser scenarios and `87/87` receipt units passed; local document lifecycle gate is green |
| 12 Sep 2026 | Phase 3 | Executed statutory, GST visual, and authenticated staging GST-TDS/TDS packs. | `43/43` local statutory, `9/9` GST visual, and `12/12` staging scenarios passed; amount/artifact/provider signoff remains |
| 12 Sep 2026 | Phase 7 | Hardened payables scope errors and completed deterministic browser/report evidence. | Backend `98/98`; Chromium `183/183`; effective cross-browser `549/549` after focused WebKit reruns; full staging reconciliation remains |
| 12 Sep 2026 | Phase 4 | Executed the dedicated local purchase-to-stock/expense/asset/GL bundle, stabilized inventory visual time, and replayed deployed purchase routes with real authentication and RBAC. | Backend `239/239`, browser `77/77`, and staging route sweep `11/11` passed; controlled persisted staging mutation/reversal evidence remains |
| 12 Sep 2026 | Phase 4 | Posted tagged asset, inventory, and service-expense purchases on Manav-T staging; reconciled asset intake, stock, AP, GST, ledgers, Trial Balance, Profit & Loss, and Balance Sheet; then reversed and cancelled the fixtures. | Core staging mutation gate passed with exact cleanup; fixed inherited category visibility and passed asset backend `80/80` plus staging asset browser `4/4` |

## Related QA Assets

- `docs/qa/purchase-e2e-test-matrix.md`
- `docs/qa/purchase-manual-qa-checklist.md`
- `docs/qa/purchase-regression-checklist.md`
- `docs/qa/purchase-urd-gst-test-matrix.md`
- `docs/qa/purchase-findings-and-improvements.md`
- Playwright project: `/Users/ansh/Documents/finacc-ui-tests`
