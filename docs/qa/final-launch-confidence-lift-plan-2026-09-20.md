# Final Launch Confidence Lift Plan

Date: 2026-09-20  
Objective: raise real end-user launch confidence to 90%+ before pilot/public launch.

This plan is intentionally workflow-first. The goal is not to add more features; it is to prove that a real business user can complete accounting, GST, purchase, sales, treasury, inventory, reporting, and access-control workflows without blocking defects, wrong accounting, stale scope, or unusable UI.

## Confidence Target

We will call the application 90% launch-confident only when:

- No open P0 defects.
- No known wrong-accounting defects.
- No known GST total mismatch defects.
- No launch-blocking UI issues on critical screens.
- P0/P1 workflows pass browser-based Playwright certification.
- Stage smoke passes after deployment.
- One realistic customer-style dataset passes source-to-report checks.
- Remaining gaps are documented as acceptable pilot backlog.

## Certification Record Format

After each phase, update the phase section with:

- Summary: what was tested/developed.
- Observations: what passed, what failed, what was surprising.
- Fixes made: code/test/doc changes.
- Evidence: command outputs, test files, screenshots if relevant.
- Residual risk: what remains and why it is acceptable or not.
- Confidence movement: previous confidence -> new confidence.
- Deployment note: not deployed / deployed to stage / verified on stage.

## Phase 0: Launch Baseline And Freeze

Purpose: define launch scope and stop uncontrolled feature expansion.

Verify:

- Launch-critical module list.
- P0/P1 defect list.
- Known backlog list.
- Stage deployment process.
- Seed/customer-like test data availability.
- Browser/device matrix.
- Playwright command matrix for certification.

Develop:

- Module certification tracker.
- P0/P1 launch defect register.
- Common Playwright tags/naming for launch tests.
- Final launch checklist.

Exit Criteria:

- Launch-critical vs backlog is clear.
- Every later phase has an agreed pass/fail gate.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 1: Core Accounting Truth

Purpose: prove that accounting entries are correct everywhere.

Verify:

- Journal voucher.
- Payment voucher.
- Receipt voucher.
- Contra/bank/cash movement.
- Debit/credit adjustments.
- Post, unpost, reverse, cancel, re-post.
- Ledger impact.
- Trial Balance balance.
- Branch/subentity isolation.
- Posting detail consistency.

Develop:

- Voucher -> posting detail -> ledger -> Trial Balance browser flows.
- Backend tests for reversal and scope isolation.
- Accounting truth matrix assertions for debit/credit balance.
- Regression tests for stale posting state and wrong branch scope.

Exit Criteria:

- No transaction can create unbalanced accounting.
- No posting can leak across entity/FY/subentity.
- Posting detail, ledger, and Trial Balance agree.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 2: Sales To Cash

Purpose: certify full AR lifecycle.

Verify:

- Sales goods invoice.
- Sales service invoice.
- Sales credit note.
- Sales debit note.
- GST output.
- TCS where applicable.
- E-invoice/e-way bill states.
- Customer outstanding.
- Customer ledger.
- AR aging.
- Receipt allocation.
- Sales register.
- Print, attachment, posting, and compliance popups.

Develop:

- Invoice -> confirm -> post -> GST -> AR -> receipt -> ledger flows.
- Credit note -> outstanding reduction checks.
- UI resilience tests for footers, smart filters, grids, and popups.
- Report-to-ledger reconciliation assertions.

Exit Criteria:

- Customer balance is correct.
- GST output is correct.
- Receipts reduce outstanding correctly.
- Print/export/popup actions are usable across desktop/tablet/mobile.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 3: Purchase To Pay

Purpose: certify full AP lifecycle.

Verify:

- Purchase goods invoice.
- Purchase service invoice.
- Purchase credit note.
- Purchase debit note.
- ITC eligible, blocked, deferred, and pending states.
- GST-TDS / income-tax TDS where enabled.
- Vendor outstanding.
- Vendor ledger.
- AP aging.
- Purchase register.
- Payment allocation.
- Footer/action layout on Windows effective 110%, tablet, and mobile.

Develop:

- Purchase -> confirm -> post -> ITC -> AP -> payment -> ledger flows.
- Credit/debit note payable and ITC adjustments.
- AP vs GL reconciliation checks.
- Footer/action layout regression tests.

Exit Criteria:

- Vendor payable is correct.
- ITC state is correct and traceable.
- Payables reports reconcile with GL.
- No critical purchase action is hidden, overlapped, or unusable.

Status: In progress

Summary:

- Purchase footer overlap and spacing issues were identified on Windows-style effective zoom.
- Footer action tests were added for purchase goods and service invoice pages.

Observations:

- Button overlap was removed, but a follow-up spacing issue appeared between `Next` and `Save`.
- The root cause was the secondary footer action group expanding across the full footer row.

Fixes Made:

- Purchase invoice, purchase credit note, and purchase debit note footer action groups were changed to content-sized flex groups.
- Explicit Playwright assertion added so `Next` and `Save` stay visually grouped when on the same row.

Evidence:

- `playwright/tests/purchase-invoice-crud.spec.ts`
- `playwright/tests/purchase-invoice-goods-crud.spec.ts`
- `src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.scss`
- `src/app/component/invoice/purchase-creditnote-invoice/purchase-creditnote-invoice.component.scss`
- `src/app/component/invoice/purchase-debitnote-invoice/purchase-debitnote-invoice.component.scss`

Residual Risk:

- Purchase credit/debit note pages still need full browser certification beyond shared footer CSS.

## Phase 4: Financial Reports Certification

Purpose: prove management and statutory financial reports match books.

Verify:

- Trial Balance.
- Balance Sheet.
- Profit & Loss.
- Ledger Book.
- Ledger Summary.
- Daybook.
- Cashbook.
- Trading Account.
- Date/FY/subentity scopes.
- Export/print/PDF/CSV.
- Refresh/back/forward/deep links.
- Dense tables and smart filters.

Develop:

- Dense report UI resilience tests.
- Scope persistence tests.
- Report totals vs ledger assertions.
- Export filename/content smoke tests.
- Browser certification across Windows effective 110%, tablet, and mobile.

Exit Criteria:

- Trial Balance is balanced.
- Balance Sheet is balanced.
- P&L agrees with ledger.
- Scope changes do not leave stale data.
- Critical report pages are usable across the launch browser matrix.

Status: Browser UI resilience lane complete

Summary:

- Financial Hub, Financial Hub Settings, Profit & Loss, Balance Sheet, Trial Balance, Ledger Summary, Ledger Book, Daybook, Cashbook, and Trading Account received first-pass UI resilience certification.

Observations:

- Hub/settings and top statements passed targeted Windows/tablet/mobile checks.
- Trial Balance and Ledger Summary now render correctly with current route-guard permissions and dense mocked data.
- Dense report testing caught an outdated mocked permission code (`reports.trialbalance.view`) before layout checks could run; the certification mock now includes the current `reports.trial_balance.view` and hub-scoped permissions.
- Ledger Book now renders correctly with selected-ledger dropdown data, report rows, voucher movement, and running balance context.
- Daybook now renders posted voucher movement with balanced debit/credit totals and visible source/posting context.
- Cashbook now renders account summaries, receipts, payments, and running-balance context for bank/cash scope.
- Trading Account now renders debit side, credit side, COGS, gross profit, valuation context, and summary cards across the launch viewport matrix.

Fixes Made:

- Playwright layout checks were added to the financial mocked spec.
- Trial Balance, Ledger Summary, Ledger Book, Daybook, Cashbook, and Trading Account mocked API payloads were added for deterministic dense-report certification.
- Financial mocked RBAC setup was aligned with the current route-guard permission contract.
- Daybook and Cashbook mocked RBAC setup was aligned with current hub-scoped route permissions.

Evidence:

- `playwright/tests/financial-hub.spec.ts`
- `npx playwright test playwright/tests/financial-hub.spec.ts --project=chromium --grep "Windows effective|statement pages are resilient|trading account pages" --reporter=line` passed on 20 Sep 2026.

Residual Risk:

- Browser UI resilience is complete for Phase 4; remaining risk is deeper live-data mathematical reconciliation/export certification beyond this UI-resilience lane.

## Phase 5: GST Source-To-Return

Purpose: certify GST from source documents to return readiness.

Verify:

- Sales GST to GSTR-1.
- Purchase ITC to GSTR-3B.
- GSTR-1 vs GSTR-3B reconciliation.
- ITC / 2B import and match.
- GST reconciliation import/run/review.
- GST Exception Dashboard.
- GST Portal lifecycle.
- E-invoice/e-way.
- GST-TDS/TCS.
- Credit note, debit note, zero, negative, duplicate, and missing-document cases.
- Entity/FY/subentity/GSTIN/return-period scope.

Develop:

- Playwright source-to-return flows.
- Reconciliation math assertions.
- Scope/race-condition tests.
- WhiteBooks/GSTN mocked lifecycle tests.
- Stage smoke tests with realistic data.

Exit Criteria:

- GST umbrella values agree with underlying workspaces.
- Reconciliation totals mathematically tie.
- No stale period/GSTIN/entity data remains after scope changes.
- GST numbers can be traced from source transaction to return workspace.

Status: In progress

Summary:

- GST Compliance Center and shared GST scope have received substantial certification coverage.
- GST Compliance Center layout resilience was added for Windows effective 110%, tablet, and mobile.
- Deterministic browser source-to-return certification now passes for sales invoices, sales credit/debit notes, export/zero-rated supply, exempt/nil/non-GST supply, purchase eligible ITC, reverse-charge purchase tax, ineligible ITC, deferred 2B ITC, GSTR-1, GSTR-3B, GSTR-1 vs GSTR-3B reconciliation, and GST Reconciliation run review.
- GST reconciliation math certification now verifies umbrella ITC tie-out and 2B decision summary against workspace detail rows.
- GSTR-2B import bridge certification now verifies a real-user browser import flow creates imported rows, auto-matches, creates a reconciliation run, and opens the review workspace.
- Stage controlled GST matrix certification now passes in both report mode and strict mode for the selected stage scope.

Observations:

- The umbrella center is stronger, but source-to-return testing remains the confidence driver.
- The local browser oracle is now strong enough to catch source-to-return regressions without depending on a live stage period being perfectly seeded.
- The selected stage GSTIN/return period now contains the full strict matrix: taxable outward supply, sales credit/debit note impact, export/zero-rated supply, nil/exempt/non-GST supply, reverse-charge purchase liability, eligible ITC, blocked/reversed ITC, deferred/pending ITC, and reconciliation evidence.

Fixes Made:

- Dedicated GST Compliance Center layout Playwright spec added.
- Source-to-return browser oracle already models the high-risk GST buckets and was rerun successfully.

Evidence:

- `playwright/tests/gst-compliance-layout.spec.ts`
- `playwright/tests/gst-compliance-scope.live.spec.ts`
- `playwright/tests/gst-compliance-card-states.live.spec.ts`
- `playwright/tests/gst-reconciliation-import-flow.spec.ts`
- `playwright/tests/gst-reconciliation-math.spec.ts`
- `playwright/tests/gst-enterprise-tax-lifecycle.spec.ts`
- `npx playwright test playwright/tests/gst-enterprise-tax-lifecycle.spec.ts --project=chromium --reporter=line` - 1 passed.
- `npx playwright test playwright/tests/gst-reconciliation-math.spec.ts --project=chromium --reporter=line` - 1 passed.
- `npx playwright test playwright/tests/gst-reconciliation-import-flow.spec.ts --project=chromium --reporter=line` - 1 passed.
- `TEST_USER_EMAIL=<stage user> TEST_USER_PASSWORD=<stage password> GST_BACKEND_URL=https://accerio.in PLAYWRIGHT_BASE_URL=https://accerio.in npx playwright test playwright/tests/gst-controlled-tax-matrix-stage-gate.live.spec.ts --project=chromium --reporter=line` - 1 passed.
- `TEST_USER_EMAIL=<stage user> TEST_USER_PASSWORD=<stage password> GST_BACKEND_URL=https://accerio.in PLAYWRIGHT_BASE_URL=https://accerio.in GST_REQUIRE_FULL_TAX_MATRIX=true npx playwright test playwright/tests/gst-controlled-tax-matrix-stage-gate.live.spec.ts --project=chromium --reporter=line` - 1 passed.

Residual Risk:

- Full GST source-to-return matrix is now stage-certified for the selected controlled period. Remaining GST risk is broader cross-browser/manual filing artifact acceptance and ongoing daily rerun discipline.

## Phase 6: Treasury And Banking

Purpose: certify bank, cash, payments, and reconciliation layer.

Verify:

- Treasury setup.
- Static bank/cash account mapping.
- Multiple bank accounts.
- Bank statement import.
- Bank reconciliation.
- Payment batch planning.
- Payment execution.
- Cheque/UPI/NEFT tracking.
- Bank charges.
- Cash forecast.
- Follow-up queue.
- Existing payment/receipt voucher compatibility.

Develop:

- Browser workflow tests for reconciliation.
- Payment batch -> voucher -> ledger trace.
- Bank statement import scenarios.
- Forecast traceability checks.
- UI speed/workflow tests for accountants.

Exit Criteria:

- Bank book vs bank statement is explainable.
- Payments trace to vouchers.
- Forecast values trace to AP/AR/payroll/open items.
- Existing payment/receipt flows remain backward compatible.

Status: In progress

Summary:

- Treasury execution layout received Windows effective 110% improvements.
- Treasury setup, bank-account-to-ledger mapping, cheque-book visibility, operational shortcuts, treasury execution, instrument register, and bank reconciliation browser workflows have first-pass deterministic certification.
- Bank reconciliation import certification now covers mapped and unmapped bank accounts, preview, validation, duplicate/invalid-row blocking, archive/start-fresh recovery, and large 100/500/1,000/5,000-line statement stability.
- Bank reconciliation workspace certification now covers exact match, many-to-one/partial match guidance, locked run blocking, unmatch audit notes, engine suggestions, missing-voucher creation, bank charge/interest suggestion review, exception actions, BRS report handoff, tablet, and mobile.

Observations:

- Treasury is newer than the core accounting modules, so real workflow certification remains important.
- The deterministic browser suite is broad enough to protect the accountant workflow locally; the next confidence step is stage/live execution against deployed data and export/report endpoints.
- A parallel Playwright run briefly produced a setup shortcut miss because multiple web servers competed for the same local port; rerunning the same treasury setup/execution/instrument pack sequentially passed 9/9.

Fixes Made:

- Treasury execution layout tightening and Playwright checks were added.

Evidence:

- `playwright/tests/treasury-execution.spec.ts`
- `playwright/tests/treasury-setup.spec.ts`
- `playwright/tests/treasury-instruments.spec.ts`
- `playwright/tests/bank-reco-import.spec.ts`
- `playwright/tests/bank-reco-workspace.spec.ts`
- `src/app/component/admin/treasury-execution-console/treasury-execution-console.component.scss`
- `npx playwright test playwright/tests/treasury-setup.spec.ts playwright/tests/treasury-execution.spec.ts playwright/tests/treasury-instruments.spec.ts --project=chromium --workers=1 --reporter=line` - 9 passed.
- `npx playwright test playwright/tests/bank-reco-import.spec.ts playwright/tests/bank-reco-workspace.spec.ts --project=chromium --workers=1 --reporter=line` - 19 passed.

Residual Risk:

- Stage/live treasury execution and bank reconciliation certification still needs to be run after deployment with the live `treasury.live.spec.ts` and `bank-reco.live.spec.ts` gates.

## Phase 7: Inventory And Valuation

Purpose: certify stock quantity and value.

Verify:

- Product master.
- Goods purchase stock in.
- Sales stock out.
- Stock ledger.
- Stock summary.
- Inventory valuation.
- Batch/expiry where enabled.
- Credit/debit note stock effects.
- Negative stock policy.
- GL inventory agreement.

Develop:

- Source document -> stock report tests.
- Inventory valuation vs GL checks.
- UI resilience for inventory reports.
- Browser tests for stock ledger and valuation drilldowns.

Exit Criteria:

- Stock quantity and accounting value agree.
- Inventory reports explain stock movement.
- Critical inventory screens are usable across launch browser matrix.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 8: Manufacturing

Purpose: certify production costing.

Verify:

- BOM.
- Production issue.
- Production receipt.
- WIP.
- Finished goods cost.
- Scrap/by-product.
- Manufacturing summary.
- Inventory/accounting impact.

Develop:

- BOM-to-production Playwright tests.
- Cost rollup assertions.
- Manufacturing report reconciliation.
- Reversal/cancellation tests.

Exit Criteria:

- Finished goods cost is explainable.
- WIP and finished goods accounting agree with inventory reports.
- Production reversal/cancellation does not leave orphaned cost/stock.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 9: RBAC, Scope, And Entitlements

Purpose: ensure right users see and access the right things.

Verify:

- Menu visibility.
- Route guards.
- Feature subscription.
- Setup vs operational access.
- Admin/accountant/viewer/restricted roles.
- Entity/FY/subentity switching.
- Deep links.
- Unauthorized screens.
- New-module menus for GST, Treasury, and reports.

Develop:

- RBAC browser test matrix.
- New-module menu coverage.
- Scope leakage checks.
- Unauthorized/permission-denied clarity checks.

Exit Criteria:

- No unauthorized access.
- No allowed-but-missing-menu route.
- No authorized user is blocked from launch-critical work.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 10: Global UI/UX Certification

Purpose: eliminate launch-visible UI defects.

Verify:

- Mac 100%.
- Windows effective 100/110%.
- Tablet.
- Mobile.
- Headers.
- Footers.
- Smart filters.
- Dialogs.
- Tables.
- Print/export buttons.
- Sticky bars.
- Long names/emails/GSTINs.
- Browser refresh/back/forward.

Develop:

- Shared Playwright UI resilience helpers.
- Module-wise viewport tests.
- CSS fixes for wrapping, spacing, overflow, and sticky bars.
- Screenshot review for representative pages.

Exit Criteria:

- No launch-critical screen has overlapping, hidden, or unusable controls.
- No primary action becomes inaccessible due to viewport/zoom.
- Critical pages remain readable under Windows effective 110%.

Status: In progress

Summary:

- Shared UI resilience helpers were added and are being reused across modules.

Observations:

- Windows effective 110% has already revealed real issues that Mac 100% did not show.

Fixes Made:

- Shared Playwright layout helpers created.
- Treasury, GST, payables, sales, purchase, and financial report slices started.

Evidence:

- `playwright/support/ui-resilience.ts`

Residual Risk:

- Several launch-critical modules still need complete viewport certification.

## Phase 11: Performance And Reliability

Purpose: avoid slow or unstable customer experience.

Verify:

- Report load time.
- Large data table rendering.
- Export response time.
- Posting response time.
- API retry/error states.
- Loading/empty/error states.
- Rapid scope changes and stale data prevention.

Develop:

- Playwright timing assertions for critical flows.
- API race-condition tests.
- Stale-data prevention checks.
- Better empty/error/loading states where needed.

Exit Criteria:

- Critical workflows feel stable under realistic use.
- Old API responses do not overwrite newer user-selected scope.
- Empty/error states are distinguishable from valid zero values.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Phase 12: Final Pilot Certification

Purpose: simulate real customer launch.

Verify:

- One full customer-like dataset.
- One complete accounting month.
- Sales, purchase, payment, receipt, GST, treasury, inventory, reports.
- Stage deployment smoke.
- Browser matrix.
- Known defects reviewed.
- Rollback readiness.

Develop:

- Final certification report.
- Pilot runbook.
- Support checklist.
- Rollback checklist.
- Known limitations/backlog.

Exit Criteria:

- Pilot approval.
- Public launch blockers are zero.
- Remaining items are documented and acceptable for pilot.

Status: Pending

Summary:

- TBD

Observations:

- TBD

Residual Risk:

- TBD

## Current Next Recommended Phase

Move to Phase 6: Treasury And Banking.

Next immediate target:

1. Bank/cash source account setup and permissions.
2. Treasury execution dashboard UI resilience and workflow path checks.
3. Payment batches, cheque register, bank follow-up, and cash forecast verification.
4. Bank reconciliation import/match/review certification.
5. Report/export and mobile/tablet regression.

Reason:

- These are daily accountant trust screens.
- They are dense, table-heavy, and highly sensitive to scope and UI layout.
- Passing them materially increases end-user confidence.
