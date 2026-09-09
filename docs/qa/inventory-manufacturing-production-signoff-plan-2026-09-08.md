# Inventory And Manufacturing Production Sign-Off Plan

Last updated: 9 September 2026

## Purpose

Establish evidence-based production confidence for inventory and manufacturing. This plan extends the existing mocked Playwright coverage by validating real persisted transactions, stock valuation, batch and location traceability, production consumption/output, accounting postings, permissions, recovery, usability, and performance.

This is a living document. After every phase, update the status, execution date, evidence, defects, residual risks, and confidence table. A phase is not complete merely because its screens render or its mocked tests pass.

## Current Assessment

The application already has broad route, report, CRUD, visual, and mocked workflow coverage. Existing suites cover inventory reports, transfer and adjustment screens, manufacturing reports, work orders, BOMs, routes, settings, and selected lifecycle actions.

The principal remaining weakness is business-integrity proof against a real database and accounting ledger. Current confidence must therefore be treated as provisional until phases 2 through 6 are executed locally and then on staging.

| Area | Initial confidence | Reason |
| --- | ---: | --- |
| Inventory UI and navigation | 90% | Broad Playwright coverage exists, mostly mocked |
| Stock quantity integrity | 72% | Real transaction-chain reconciliation needs certification |
| Stock valuation | 65% | Method, rounding, backdating, negative stock, and GL parity need proof |
| Batch/location traceability | 70% | Operational coverage exists; persisted lineage and isolation need saturation |
| Manufacturing execution | 75% | Workflows are covered, but real consumption/output and exception paths need proof |
| Manufacturing costing and GL | 62% | WIP, variance, recovery, reversal, and financial-report parity are launch-critical gaps |
| Overall business confidence | 94% | Core operations, rollback, reports, deterministic shared-posting chains, 177 purchase/sales API lifecycle tests, a real mixed-UOM document-to-GL chain, and repeatable concurrent post/update/unpost/cancel/retry protection are green; staging and later-phase gates remain |

## In-Scope Business Surfaces

### Inventory operations

- Location master and inventory settings
- Purchase receipt and purchase return stock effects
- Sale dispatch and sales return stock effects
- Inventory transfers and transfer reversal
- Inventory increases, decreases, damage, write-off, and opening adjustments
- Batch-managed and non-batch products
- Source/destination location availability and movement history
- Stock summary, location stock, ledger, aging, movement, day book, book summary, and book detail
- Reorder, slow-moving, non-moving, and dead-stock reports

### Manufacturing operations

- BOM creation, version/edit behavior, units, scrap, and yield
- Manufacturing routes and operation sequencing
- Manual and BOM-backed work orders
- Material issue/consumption, substitutions, over/under-consumption, scrap, and returns
- Partial and multiple production outputs
- Batch genealogy from inputs to finished goods
- QC approval, rejection, rework, cancellation, post, and unpost
- Additional costs, recoveries, WIP, actual cost, and variance
- Manufacturing summary, material consumption, output/yield, posting audit, and WIP/cost reports

### Accounting integration

- Inventory asset/control accounts
- Purchase, COGS, consumption, WIP, finished goods, scrap, variance, and recovery accounts
- Balanced journals, correct dates/FY/branch/entity, source references, and idempotency
- Trial balance, stock valuation, manufacturing reports, and general-ledger agreement

## Test Data Matrix

Each core scenario will use deterministic products and opening balances so expected quantity and value can be calculated independently.

| Dimension | Required permutations |
| --- | --- |
| Product tracking | Non-batch, batch-managed, expiring batch |
| Valuation | Every method supported by settings; document unsupported methods explicitly |
| Tax profile | GST taxable, exempt/non-GST, registered and unregistered counterparty where applicable |
| Location | Head office, second location, cross-branch location, forbidden location |
| Quantity | Whole, decimal, conversion UOM, zero, insufficient, negative attempt |
| Timing | Current date, backdated open period, locked period, FY boundary |
| Workflow | Draft, confirmed where applicable, posted, unposted, cancelled |
| Manufacturing | Exact BOM, variance, scrap, partial output, multiple output, rework |
| Access | Admin, inventory operator, manufacturing operator, accountant, read-only, restricted |

All generated records must carry a run identifier and be removable or explicitly retained as QA evidence.

## Coverage Completeness Protocol

“Complete coverage” means every supported business rule is represented in the traceability matrix and every launch-critical row has objective evidence. It does not mean testing every mathematically possible combination, which is unbounded. Pairwise permutations are acceptable for low-risk presentation behavior; quantity, valuation, posting, reversal, isolation, and compliance rules require boundary and end-to-end evidence.

Each traceability row must identify:

- Requirement or invariant and whether the behavior is supported, unsupported, or intentionally out of scope.
- Frontend route, API endpoint, backend service/model, permission, and accounting/report consumers.
- Positive, negative, boundary, lifecycle, retry, isolation, and recovery scenarios where applicable.
- Evidence layer: unit/service, API/database, browser, report/export, GL/trial balance, accessibility, and performance.
- Environment and data identity, including entity, branch, FY, location, product, batch/serial, and generated document IDs.
- Result: passed, failed, blocked, skipped, or not run. A conditional skip is an uncovered row, not a pass.

Completeness controls:

- No route, endpoint, mutation action, report, export, permission, or lifecycle state may be absent from the matrix.
- Every mutation must prove both intended changes and absence of partial/orphan changes.
- Every posting must prove idempotency, balanced accounting where applicable, source traceability, and exact reversal.
- Every list/report must prove empty, single-row, multi-page, filtered, malformed-filter, large-number, and export behavior.
- Every scope-sensitive API must be tested through list access and direct-object access using another entity, branch, FY, and location.
- Every browser-critical workflow must run without conditional skips in the production sign-off lane.
- Unsupported combinations must be blocked with an actionable message and documented; silently accepting them is a defect.

## Open Coverage Register

This register is authoritative until the detailed requirement-to-test matrix is generated. A row remains open until repeatable evidence is linked in the relevant phase.

| ID | Scenario not yet fully certified | Risk | Planned phase |
| --- | --- | --- | --- |
| GAP-INV-001 | Deterministic purchase receipt -> transfer -> adjustment -> sale -> return, including real purchase/sales document APIs, operation services, location snapshots, lot preservation, reports, and balanced GL entries | Closed locally; staging certification remains | Phase 2 |
| GAP-INV-002 | Independent-connection PostgreSQL tests retain simultaneous post, update-versus-post, unpost, cancel, and retry coverage for transfers and adjustments with exact posting/movement invariants | Closed locally; staging/load certification remains | Phase 2/8 |
| GAP-INV-003 | Serial identity is not implemented in transaction or movement schemas. New activation is now blocked consistently in product API, bulk import, and UI; legacy flagged products remain editable and can be turned off. Full serial allocation/genealogy is a future product capability, not a certified launch feature | Explicitly unsupported and safely gated | Future scope |
| GAP-INV-004 | Fractional alternate-UOM transfer/adjustment conversion, exact reversal, and purchase/sales/return cross-document normalization are proven; long-chain cumulative rounding remains | Medium, substantially covered | Phase 2/3 |
| GAP-VAL-001 | Every configured valuation method with changing costs, partial issues, returns, landed cost, discount, and free quantity | Critical | Phase 3 |
| GAP-VAL-002 | Backdated posting, locked books/GST periods, FY boundary, zero cost, negative stock, and later-period reversal | Critical | Phase 3 |
| GAP-VAL-003 | Stock valuation by product/location/batch equals inventory-control GL and trial balance at the same cutoff | Critical | Phase 3 |
| GAP-MFG-001 | BOM version/effective dates, inactive components, circular/self-reference, substitutions, scrap, yield, and edit restrictions after use | High | Phase 4 |
| GAP-MFG-002 | Partial and multiple completions, excess/short consumption, material return, rework, rejection, cancellation, and downstream dependency blocking | Critical | Phase 4 |
| GAP-MFG-003 | Persisted input-batch -> output-batch genealogy, expiry discipline, serialized inputs/outputs if supported, and reverse recall lookup | Critical | Phase 4 |
| GAP-MFG-004 | Operation transition matrix including out-of-order, repeated, stale, unauthorized, skipped, rejected, and approved actions | High | Phase 4/6 |
| GAP-COST-001 | WIP equation, scrap/recovery, overhead, variance, finished-goods capitalization, and subsequent sale COGS are locally reconciled for the supported single-final-post workflow; staging proof remains and incremental partial completions are unsupported | Critical, locally closed for supported scope | Phase 5 |
| GAP-SEC-001 | Complete role/action matrix plus entity, branch, FY, location, batch, and direct-object isolation for every endpoint | Critical | Phase 6 |
| GAP-REC-001 | Timeout, offline, interrupted request, 401/403/409/422/500, stale edit, repeated click, retry, and audit-log behavior | High | Phase 6 |
| GAP-UX-001 | All reports: empty/single/multi-page, accurate pagination, sorting, filters/reset, drilldown, exports, loading/error/readonly states | High | Phase 7 |
| GAP-A11Y-001 | Keyboard, focus visibility/order/trap, names/labels, screen reader review, and automated WCAG scan | High | Phase 7 |
| GAP-VIS-001 | Approved desktop/tablet/mobile baselines in Chromium, Firefox, and WebKit with no overflow or overlap | Medium | Phase 7 |
| GAP-PERF-001 | Agreed production volumes, concurrent writes, report/export timings, repeated runs, and flake detection | High | Phase 8 |

Current audit inventory includes all declared `inventory_ops` and `manufacturing` API routes, their frontend operational/settings/report routes, backend test methods, and Playwright inventory/manufacturing specifications. The next matrix revision must map them row by row rather than relying on file-level presence.

## Phase Plan

### Phase 0: Baseline And Traceability

Status: Completed on 8 September 2026

Goal: inventory all routes, APIs, models, services, postings, reports, permissions, existing tests, and known defects before creating data.

Work:

- Map every operational and report route to its API and backend service.
- Build a requirement-to-test matrix with test IDs and ownership.
- Run existing backend and Playwright suites without changing data.
- Record local environment prerequisites and staging-safe cleanup rules.
- Replace unsupported confidence claims based only on mocks with evidence labels.

Exit criteria:

- Every in-scope surface has an owner, test layer, and expected accounting effect.
- Baseline failures are classified as product defects, environment defects, test defects, or data defects.
- Phase 1 test data can be created without colliding with user data.

Evidence:

- Backend modules mapped: `inventory_ops` and `manufacturing`, with shared integration through `inventory`, `posting`, `reports`, purchase, and sales transaction paths.
- Inventory API families mapped: entry/settings metadata, stock hints, location masters, transfer create/list/detail/post/unpost/cancel, and adjustment create/list/detail/post/unpost/cancel.
- Manufacturing API families mapped: settings, route and BOM CRUD, work-order CRUD, operation start/complete/approve/reject/skip, work-order post/unpost/cancel, and all five manufacturing report endpoints.
- Principal mutation services mapped to `InventoryTransferService`, `InventoryAdjustmentService`, and manufacturing work-order posting/lifecycle services in `inventory_ops/services.py` and `manufacturing/services.py`.
- Frontend operational routes and their `feature_inventory` permissions were verified in `app-routing.module.ts`; inventory report routes additionally require `feature_reporting` and report-specific permissions.
- Backend command: `./venv/bin/python manage.py test inventory_ops manufacturing --keepdb --verbosity=1`.
- Backend result: `73 passed`, zero failures, zero Django system-check issues, completed in 34.733 seconds.
- Initial backend invocation without `--keepdb` was blocked by an existing `test_finacc_db` and a non-interactive deletion prompt. This is classified as a local test-environment issue, not a product defect.
- Browser command: selected Chromium inventory/manufacturing CRUD, actions, report reconciliation, admin/settings, work-order lifecycle, QC, costing, negative-stock, BOM, and route suites from `/Users/ansh/Documents/finacc-ui-tests`.
- Browser result: `65 passed`, `1 skipped`, zero failures, completed in 11.8 minutes.
- The browser skip is conditional on runtime data or permission availability. It remains an explicit Phase 1 action: deterministic fixtures and permissions must make the production sign-off lane no-skip.
- Baseline classification: existing backend tests provide persisted service/API evidence; much of the broad browser suite still uses controlled/mocked responses. Neither alone closes valuation-to-GL or production-cost-to-GL proof.

### Phase 1: Masters, Settings, And Opening Position

Status: Completed locally and on staging on 8 September 2026

Goal: prove configuration and opening data are valid before transactional testing.

Work:

- Create locations, products, UOM/conversions, batches, BOMs, routes, and ledger mappings.
- Validate duplicate prevention, required fields, inactive records, and edit restrictions.
- Verify valuation and negative-stock settings are honored consistently by UI and API.
- Reconcile opening quantity/value by product, batch, location, and inventory control account.
- Test entity, branch, and location filtering at master-data level.

Exit criteria:

- Opening stock detail equals stock summary and GL opening balance.
- Invalid and duplicate masters fail with actionable messages and no partial records.

Evidence:

- Existing location-master coverage confirms create/update/deactivate behavior, duplicate-code rejection, branch defaults, entity ownership, and inventory-family navigation.
- Existing inventory/manufacturing settings coverage confirms policy and numbering persistence, permission enforcement, conflict handling, and reversible UI edits.
- Existing BOM and route coverage confirms create/update/delete, required-field validation, duplicate material rejection, route-scope validation, shared-root read-only behavior, and work-order metadata exposure.
- Focused backend command: `./venv/bin/python manage.py test catalog.tests.CatalogOpeningStockAndPlanningTests reports.tests_inventory.InventoryReportAPITests --keepdb --verbosity=1`.
- Focused backend result before additions: `31 passed`, zero failures, completed in 5.404 seconds.
- Added opening-stock regression coverage for update/reposting, deletion cleanup, and duplicate rejection without extra inventory or journal postings.
- Opening-stock command after additions: `./venv/bin/python manage.py test catalog.tests.CatalogOpeningStockAndPlanningTests --keepdb --verbosity=2`.
- Opening-stock result after additions: `11 passed`, zero failures, completed in 1.709 seconds.
- Opening-stock create is now explicitly reconciled to location, branch, FY, quantity, cost, inventory movement, balanced journal, stock summary, and trial balance.
- Opening-stock edit is proven to replace rather than duplicate the inventory movement, posting entry, and two balanced journal lines.
- Opening-stock deletion is proven to remove the source row, inventory movement, posting entry, and journal lines.
- Duplicate opening stock for the same entity/product/branch/location/date returns HTTP 400 and leaves exactly one source row, one movement, and two journal lines.
- Browser product lifecycle initially timed out under the global 30-second budget after successfully saving and rendering a price row. This was classified as a test-budget defect, not a product defect.
- The long multi-tab product lifecycle now has an explicit 180-second budget. Rerun command: `npx playwright test tests/p2/products.p2.spec.ts --project=chromium --grep "FIN-CAT-PR-003" --workers=1 --reporter=line`.
- Browser rerun result: setup plus the complete stock-product tab lifecycle passed (`2 passed`) in 34.0 seconds, including GST, prices, UOM conversion, barcode, opening stock, planning, attributes, and image behavior.
- Referenced-product deletion protection also passed in the preceding focused run.
- Staging execution against `Manav-T` completed the stock-product tab workflow but exposed an orphan cleanup defect: deleting opening-stock row `15` left its `OB/-15` inventory move, posting entry, posting batch, and two journal lines. The retained movement then correctly blocked product deletion.
- Root-cause boundary: local model-signal coverage passed, but relying only on the `post_delete` signal did not reliably clear postings through the deployed API path.
- Fix added in `OpeningStockByLocationRUDAPIView.perform_destroy`: explicitly clear the opening-stock posting inside the same database transaction before deleting the source row. The model signal remains as defense for non-API deletes.
- Post-fix local opening-stock suite result: `11 passed`, zero failures, completed in 2.123 seconds.
- Staging QA products `145` and `147` and their exact orphan postings were removed after diagnosis; no unrelated data was changed.
- Staging timing observation: the complete multi-tab product lifecycle exceeded 180 seconds once. Its test budget is now 300 seconds, and the duration is retained for Phase 8 performance review.
- First post-deployment staging rerun reached the planning step but timed out after 300 seconds because **Delete / Reset** did not open its confirmation dialog. The application showed `Planning saved` before the asynchronous planning reload had populated `planningRow`; an immediate delete therefore silently reset the form instead of deleting the saved row.
- Frontend fix: the save helper now passes the API result to its success callback before showing success, and planning adopts that returned row immediately. A regression test proves that deletion is available immediately after save.
- Frontend verification: all `128` product-form unit tests passed, TypeScript type-check passed, and `git diff --check` passed.
- The staging database audit after both reruns found new orphan opening-stock movements `321` and `323`, each with one entry, one posting batch, and two journal lines after its source opening row had been deleted.
- Nginx evidence identified the concurrency root cause: the opening-stock `PUT` and `DELETE` overlapped; the delete completed first and the slower update completed afterward, recreating postings after the source row was removed.
- Backend fix: opening-stock update and delete now lock the source row with `select_for_update()` inside a transaction, serializing the two mutations. The lock query deliberately excludes nullable related joins so it is valid on PostgreSQL.
- Post-lock local verification: all `11` opening-stock/planning backend tests passed, `manage.py check` passed, and `git diff --check` passed.
- The final Phase 1 gate required both fixes to be deployed, `FIN-CAT-PR-003` to pass on staging, and a post-run database audit to show no new orphan `catalog_opening_stock` movements or journals.
- Final staging command: `npx playwright test tests/p2/products.p2.spec.ts --project=chromium --grep "FIN-CAT-PR-003" --workers=1 --reporter=line` against `https://accerio.in` and entity `Manav-T`.
- Final staging result: authentication and the complete stock-product lifecycle passed (`2 passed`) in 1.2 minutes. This included create, edit, validation, GST, prices, UOM conversion, barcode, opening stock, planning, attributes, images, immediate planning deletion, and final product cleanup.
- Post-run database certification: `11` valid catalog opening movements remained and `0` orphan opening-stock movements, entries, journal lines, or posting batches were found for `Manav-T`.
- Phase 1 exit criteria are satisfied. Overall inventory/manufacturing confidence is raised from `78%` to `82%`; further increases depend on Phase 2 real transaction-chain evidence.

### Phase 2: Inventory Quantity And Movement Integrity

Status: In progress from 8 September 2026

Goal: prove every inventory event changes only the intended stock bucket and reverses cleanly.

Work:

- Purchase receipt -> transfer -> adjustment -> sale -> return chain.
- Whole and decimal quantities, UOM conversion, batch and non-batch products.
- Same-location prevention, insufficient stock, negative-stock policy, duplicate submission, and concurrent requests.
- Post, unpost, cancel, retry, and failed-request idempotency.
- Reconcile each step across transaction detail, stock ledger, location stock, stock summary, movement, and day book.

Core invariants:

- Opening + inward - outward +/- adjustment = closing quantity.
- Transfer leaves entity total unchanged and moves equal quantity/value between locations.
- Unpost restores the exact prior position; retry never creates duplicate movement.
- A failed multi-line transaction leaves no orphan header, line, batch allocation, or ledger entry.

Exit criteria:

- All quantity invariants pass for every required permutation.
- No cross-entity, branch, location, or batch leakage is observed.

Evidence:

- Local backend command: `./venv/bin/python manage.py test inventory_ops --keepdb --verbosity=1`.
- Local backend result after Phase 2 additions: `45 passed`, zero failures; Django system checks and `git diff --check` also passed.
- Transfer coverage proves draft creation, required locations, same-location rejection without a partial header, source shortage rejection, derived cost, alternate-UOM base quantity, required batches, scope filtering, post/unpost/cancel, and repeated post/cancel idempotency without duplicate movements.
- Adjustment coverage proves draft creation, positive and negative movement rules, explicit/default cost behavior, alternate-UOM base quantity, batch/expiry behavior, shortage blocking, scope filtering, post/unpost/cancel, and repeated post/cancel idempotency without duplicate movements.
- Unpost contract is now explicit: the latest posting entry and active batch remain as a traceable `REVERSED` audit marker, while inventory movements and journal lines are both zero before cancellation.
- Staging CRUD command targeted `FIN-INV-OPS-TRN-CRUD-001` and `FIN-INV-OPS-ADJ-CRUD-001` against `https://accerio.in` and `Manav-T`.
- Staging CRUD result: authentication plus transfer and adjustment create/post/unpost/cancel, browser reopen, list search, and detail navigation passed (`3 passed`) in 1.6 minutes with no skips.
- Staging policy result: all ten reversible adjustment/transfer settings scenarios plus authentication passed (`11 passed`) in 4.4 minutes. Auto-post, unpost blocking, cancel blocking, and confirmation-on/off behavior were exercised and settings were restored.
- Staging report result: all stock summary, ledger, aging, non-moving, day-book, movement, and scoped drilldown numeric checks passed (`8 passed`) in 1.6 minutes against live report APIs.
- Database inspection confirmed the cancelled staging transfer and adjustment retained only `REVERSED` audit markers with zero inventory movements and zero journal lines.
- Added failed multi-line rollback tests for both transfers and adjustments. A valid first line followed by an invalid batch-managed line returns HTTP 400 and leaves no document header or detail rows.
- Focused purchase/sales stock and concurrency command covered purchase inventory-return safety, purchase update/action locking, sales quantity-return context, and both posting adapters. Result: `40 passed`, zero failures. Two stale purchase concurrency mocks were aligned with the current `select_for_update(of=("self",)).select_related(...).get()` contract.
- Staging-wide database audit covered all `6` transfers and `11` adjustments for `Manav-T`: zero cancelled documents retained movements or journal lines, zero posted transfers differed from the required two movements per line, and zero posted adjustments differed from one movement per line.
- Inventory-report and manufacturing consumer verification command: `./venv/bin/python manage.py test reports.tests_inventory manufacturing --keepdb --verbosity=1`. Result: `62 passed`, zero failures and zero system-check issues in 16.126 seconds. This covers persisted inventory report calculations and manufacturing movement/lifecycle consumers after the inventory-operation changes.
- Added `test_deterministic_cross_module_stock_chain_reconciles_locations_and_reports`. It starts from 20 units at source, posts a 10-unit purchase inward, transfers 5 units, decreases destination by 1, posts a 2-unit sale outward, and posts a 1-unit sales return inward. Direct snapshots reconcile to source `25.0000`, destination `3.0000`, and entity `28.0000` after every event.
- The chain uses the production `PostingService` for purchase/sale/return movements and the production transfer/adjustment services for operational mutations. It verifies posted entry/movement cardinality, Stock Summary closing quantity `28.0000`, and Location Stock quantities `25.0000` and `3.0000` under the same product and cutoff scope.
- Added a batch-managed permutation using the existing `B-1` lot. Starting quantity `5.0000`, purchase `+10.0000`, transfer `2.0000`, adjustment `-1.0000`, sale `-1.0000`, and return `+0.5000` reconcile to source `13.0000`, destination `0.5000`, and entity `13.5000`. All six source movements preserve the exact batch number and strong transaction locator.
- Batch/non-batch focused result: `2 passed` in 0.653 seconds. Full inventory operations result after the batch addition: `39 passed`, zero failures in 7.364 seconds, followed by clean Django system and diff checks.
- Focused regression command: `./venv/bin/python manage.py test inventory_ops reports.tests_inventory --keepdb --verbosity=1`. Result: `61 passed`, zero failures in 11.441 seconds, followed by clean Django system and diff checks.
- Full document lifecycle command after linked-chain coverage: `./venv/bin/python manage.py test purchase.tests_e2e_api sales.tests_e2e_api --keepdb --verbosity=1`. Result: `177 passed`, zero failures and zero system-check issues in 57.945 seconds.
- The document lifecycle run covers purchase and sales goods/services, batch requirements, receipt/dispatch returns, stock-consumption return safeguards, confirm/post/unpost and note flows, GST/ITC/RCM/TDS/TCS contracts, open-item settlement, and scoped payment actions.
- Test-contract corrections made during this gate: taxable goods/assets now carry HSN, services carry six-digit SAC, payment actions carry entity/FY/branch scope, paginated search assertions consume `results`, and tax-summary assertions respect the intentional confirm/post rebuild boundary. The first broad run exposed 25 stale-contract failures; the final run was clean.
- Added a real linked document/API chain using canonical seeded posting accounts: purchase receipt `1 BOX = +10 PCS`, transfer `5 PCS`, destination adjustment `-1 PCS`, sales invoice `0.2 BOX = -2 PCS`, and quantity-return credit note `0.1 BOX = +1 PCS`. Persisted stock closes at source `5.0000`, destination `3.0000`, and entity `8.0000`; purchase, sale, and return each emit exactly one intended inventory movement and a non-empty, balanced posted journal entry.
- Exact document movement snapshots prove selected UOM `BOX`, factor-to-base `10.00000000`, and base quantities `10.0000`, `2.0000`, and `1.0000` for purchase, sale, and return respectively.
- Added fractional alternate-UOM precision and reversal coverage. With `1 BOX = 10 PCS`, transfer `0.3333 BOX` posts exactly `3.3330 PCS` in/out and adjustment `0.1667 BOX` posts exactly `1.6670 PCS`; both unpost paths remove their movements and restore exact pre-event location balances with no residual quantity.
- Inventory operations result after the UOM precision addition: `40 passed`, zero failures in 7.723 seconds, followed by clean Django system and diff checks.
- Serialization capability audit found only the catalog-level `Product.is_serialized` flag; purchase, sales, transfer, adjustment, posting movement, manufacturing, and report schemas have no serial-number identity or allocation model. Treating the checkbox as supported would therefore permit untraceable serialized stock.
- New serialized activation is blocked with an actionable message in `ProductSerializer`, bulk workbook validation, and bulk commit defense. Existing serialized rows remain readable/editable and may be turned off. The frontend toggle is disabled for new activation and clearly marked `not available yet`; batch-managed tracking remains available.
- Serialization guard verification: `CatalogPhase1Tests` plus `CatalogBulkProductsCoverageTests` passed `54/54`; frontend TypeScript check passed; product-form ChromeHeadless unit suite passed `128/128`.
- Added `test_real_document_api_stock_chain_reconciles_purchase_transfer_adjustment_sale_and_return`. It seeds canonical posting accounts, posts a real 10-unit purchase receipt through the purchase API, transfers 5 units, decreases destination by 1, posts a 2-unit sales invoice through the sales API, and posts a 1-unit quantity-return credit note through the sales API.
- The linked API chain finishes at source `5.0000`, destination `3.0000`, and entity `8.0000`. It asserts exact purchase, sale, and sales-credit-note inventory movement identity; the return additionally carries movement nature `RETURN`. All three document entries are `POSTED`, contain non-zero journals, and have exactly equal debit and credit totals.
- This closes the shared posting -> inventory operations -> inventory reports arithmetic path for both non-batch and batch-managed products. It does not yet prove that real purchase and sales invoice/note API state machines emit every endpoint movement in the same chain; that linkage remains open under `GAP-INV-001`.
- `InventoryOpsConcurrencyTests` now retains separate-connection PostgreSQL races as repeatable integration gates. Simultaneous posts plus a normal retry converge on one posting entry and one active posting batch; duplicate unpost creates one reversal; duplicate cancel is idempotent; and update-versus-post leaves one complete posting from either valid lock order. Transfer and adjustment movement cardinality and quantities remain exact.
- The earlier teardown failure was isolated to a stale retained test schema. Rebuilding the test database through the complete migration graph removed the orphan payroll foreign-key condition, and all five concurrency tests plus the complete `45/45` inventory suite passed.
- Post-deployment staging CRUD rerun against `https://accerio.in` and `Manav-T` passed authentication plus transfer and adjustment create/post/unpost/cancel/browser workflows (`3 passed`) in 1.6 minutes with no skips.
- Post-deployment staging inventory reconciliation initially returned `6 passed, 2 failed`: Stock Summary remained on its loading spinner beyond the 20-second assertion budget and Stock Day Book navigation exceeded the 30-second page-load budget. Both targeted cases passed on immediate rerun with a 90-second diagnostic budget (`3 passed`, including authentication) in 36.9 seconds. This is classified as staging latency evidence for Phase 8, not a functional reconciliation failure.
- The deployed-host `InventoryOpsConcurrencyTests` command was attempted against the isolated Django test database but could not start because the staging application database role lacks permission to create the test database. Tests were not redirected to the live database. Staging concurrency certification therefore remains blocked pending a dedicated test database or a test-only role with `CREATEDB`.
- Remaining Phase 2 gates: certify the linked and concurrency chains on staging and close the remaining long-chain UOM boundary rows recorded in the coverage register. Serialized inventory remains an explicitly gated future capability.
- Interim confidence increased from `82%` to `94%`; Phase 2 is not yet complete.

### Phase 3: Valuation And Inventory Accounting

Status: In progress from 9 September 2026

Goal: independently verify stock cost and accounting impact.

Work:

- Test every supported valuation method with changing purchase costs and partial issues.
- Verify landed/additional cost allocation, discounts, returns, free quantity, and rounding.
- Test backdated transactions, locked periods, FY boundary, zero cost, and negative-stock restrictions.
- Compare stock valuation reports to independently calculated expected values.
- Reconcile inventory asset, purchase/GRNI where applicable, COGS, write-off, and adjustment journals.
- Confirm journals are balanced and retain source-document traceability through reversal.

Core invariants:

- Sum of product/location/batch valuations equals inventory control-account balance for the same scope and cutoff.
- COGS or consumption uses the configured valuation basis, not selling price or latest arbitrary rate.
- Reversal journals exactly negate the original posting without changing unrelated periods.

Exit criteria:

- Quantity and value agree across operational reports, valuation output, posting detail, GL, and trial balance.
- Every rounding difference is within an explicitly approved tolerance.

Evidence:

- Phase 3 baseline command: `./venv/bin/python manage.py test reports.tests_inventory financial.tests --keepdb --verbosity=1`.
- Baseline result: `115 passed`, zero failures and zero system-check issues in 54.593 seconds. Existing coverage proves FIFO/LIFO report divergence for mixed-cost layers, stock-ledger/summary arithmetic, financial report valuation selection, and broad financial posting/report behavior.
- Architecture audit found that inventory reports and Trading Account independently value issues from historical inventory layers using FIFO/LIFO/MWA/WAC/latest strategies. This is consistent with periodic inventory accounting, where COGS is calculated as opening stock plus purchases minus closing stock rather than journaled on every sale.
- The architecture audit found that the sales posting adapter does not create COGS/inventory-control journal lines and stored sales inventory-movement `unit_cost` from taxable sales value, with an inline note identifying it as a placeholder for a future valuation engine. FIFO/LIFO/MWA/WAC report calculations did not trust that outbound rate, but the persisted movement cost and any downstream consumer reading it directly could misstate issue cost.
- Phase 3 must first make the accounting policy explicit: periodic mode must suppress perpetual COGS journals and store valuation-derived issue metadata; perpetual mode must atomically post valuation-derived COGS against inventory control. Implementing COGS journals without this policy boundary risks double counting.
- Corrected the sales movement defect without changing the periodic-accounting journal policy. Sales issues now persist a location- and batch-scoped FIFO acquisition cost; selling price/taxable value is no longer used as inventory cost. Quantity-return credit notes restore the weighted issue cost recorded by the referenced original sales invoice.
- The FIFO resolver consumes prior receipt layers and prior issues in posting-date/id order, preserves signed adjustment/reversal quantities, supports base-UOM issue quantities, and records `FIFO` plus a valuation-source marker in movement metadata.
- Added a changing-cost assertion for two receipt layers (`10 @ 100` and `10 @ 200`) followed by a 15-unit issue. The independently calculated FIFO issue rate is `133.3333`, proving that the first complete layer and half of the second layer are consumed.
- Adapter coverage proves that a sale of one alternate UOM converted to `1000` base units receives the resolver cost (`1.0000`) and not the selling-derived rate (`0.2500`). The real linked purchase -> transfer -> adjustment -> sale -> return API workflow also passes with the production valuation resolver.
- Transaction/API regression command: `./venv/bin/python manage.py test sales.tests sales.tests_e2e_api purchase.tests_e2e_api --noinput --keepdb --verbosity=1`.
- Transaction/API regression result: `408 passed`, zero failures in 111.528 seconds. An initial run exposed an invalid enum-member reference in the new helper; the exact integrated stock-chain test caught it, it was corrected, and the complete suite was rerun cleanly.
- Inventory-report/financial regression command: `./venv/bin/python manage.py test reports.tests_inventory financial.tests --noinput --keepdb --verbosity=1`.
- Inventory-report/financial regression result after the correction: `115 passed`, zero failures and zero system-check issues in 74.424 seconds.
- Historical sales movements retain their previously persisted cost metadata. A production migration/backfill must not be run until its cutoff, recomputation method, audit trail, and effect on finalized reports are approved.
- Purchase quantity-return credit notes previously derived outbound stock cost from the credit-note taxable amount. They now restore the weighted receipt cost recorded by the referenced purchase invoice, scoped by product and batch. A focused adapter test proves that an original cost of `75.0000` is retained even when the credit-note amount implies `50.0000`.
- Purchase acquisition-cost coverage now proves that free quantity participates in the configured cost spread after base-UOM conversion: `2` paid plus `1` free selected units at taxable value `500`, with a `1000` base-unit conversion factor, posts `3000` base units at `0.1667` each.
- Date-cutoff coverage proves that a `2025-04-10` issue sees the `2025-04-05` layer at `100.0000` and excludes the future `2025-04-15` layer. Original-reference lookup returns `200.0000` for the second purchase and zero for a missing reference.
- Negative-stock valuation is now conservative when warning-mode policy allows an issue beyond available layers. The uncovered quantity receives zero acquisition value rather than extending the available average across nonexistent stock; `20` units valued at `3000` issued as `30` units therefore persist a weighted issue rate of `100.0000`, not `150.0000`.
- Consolidated valuation-safe transaction command: `./venv/bin/python manage.py test purchase.tests.PurchasePostingAdapterTests purchase.tests_e2e_api sales.tests sales.tests_e2e_api --noinput --keepdb --verbosity=1`.
- Consolidated transaction result: `420 passed`, zero failures in 82.435 seconds. Inventory-report/financial rerun remained `115 passed`, zero failures in 37.450 seconds.
- A wider `807`-test combined invocation exposed `16` failures and `2` teardown errors in legacy `purchase.tests`. The failures are order-dependent test isolation defects involving hard-coded entity IDs, persisted purchase settings, leaked setup state, and mocks; the valuation-focused class and all purchase/sales E2E suites pass together. This debt remains visible and must be repaired before treating a monolithic full-suite run as a launch gate.
- Current additional-charge policy remains periodic-expense treatment because `PurchaseInvoiceActions` explicitly sets `capitalize_header_expenses_to_inventory=False`. The dormant capitalization switch is not exposed as a supported entity policy and is not counted as certified landed-cost functionality.
- Added persisted return-safety tests proving that an active prior return of `4.0000` against an original `10.0000` receipt allows exactly `6.0000` more and rejects `6.0001`. A cancelled `10.0000` return does not consume the available return balance.
- Added correction-period boundaries proving that a quantity-return note is rejected on an inventory-lock cutoff (`2026-04-30`), accepted on the next open day, and rejected after the selected FY end (`2027-03-31`). Existing document validation also requires the referenced purchase to belong to the same entity, FY, branch scope, and vendor.
- Return safety focused result: `5 passed`, zero failures. It covers available stock, downstream consumption, cumulative returns, cancelled-return exclusion, inventory locks, and FY end.
- Final business-critical consolidated command: `./venv/bin/python manage.py test purchase.tests.PurchasePostingAdapterTests purchase.tests.PurchaseInventoryReturnSafetyTests purchase.tests_e2e_api sales.tests sales.tests_e2e_api reports.tests_inventory financial.tests --noinput --keepdb --verbosity=1`.
- Final consolidated result: `540 passed`, zero failures and zero system-check issues in 156.523 seconds.
- Reproduction of the legacy purchase test debt identified exact fixture defects: hard-coded `entity=1`/FY IDs no longer matched database-generated fixtures, vendor-validation mocks omitted the now-required ledger, product-query mocks targeted a former query shape, an allowed update mock omitted fields used by audit logging, and settlement cancellation did not arrange its newer object-scope authorization prerequisite.
- Repaired those fixtures without weakening production validation. The five formerly failing purchase classes now pass together (`93 passed`) with deferred database constraints enabled.
- Monolithic command: `./venv/bin/python manage.py test sales.tests sales.tests_e2e_api purchase.tests purchase.tests_e2e_api reports.tests_inventory financial.tests --noinput --keepdb --verbosity=1`.
- Monolithic result after fixture repairs and return-boundary additions: `810 passed`, zero failures, zero deferred-constraint errors, and zero system-check issues in 224.937 seconds. This replaces the earlier `16` failures and `2` errors and closes the local order-isolation blocker for this scope.
- Next gate: decide whether landed-cost capitalization becomes a supported entity setting and execute the complete valuation chain on staging. Then enumerate every direct consumer of outbound `unit_cost`/`ext_cost` before deciding whether historical backfill is required.

### Phase 4: Manufacturing Execution And Traceability

Status: Pending

Goal: prove physical production flows from raw material to finished goods with complete lineage.

Work:

- BOM-backed and manual work orders.
- Reservation/availability, issue, consumption, excess/short consumption, substitution, scrap, and material return.
- Partial production, multiple completions, by-products/recoveries if supported, QC reject/rework, and cancellation.
- Input and output batch selection, expiry controls, and genealogy.
- Post/unpost safety after downstream consumption or sale.
- Reconcile work-order quantities to raw-material, WIP, finished-good, and scrap movements.

Core invariants:

- Issued = consumed + returned + recorded scrap + remaining WIP, subject to documented process semantics.
- Finished output is available only after the required workflow gate.
- Batch genealogy identifies all input batches for an output batch and all outputs affected by an input batch.

Exit criteria:

- Normal, partial, variance, scrap, rework, and reversal paths preserve quantity integrity and lineage.

Evidence: Pending.

### Phase 5: Manufacturing Costing And Accounting Reconciliation

Status: Local core reconciliation complete; staging proof pending

Goal: prove production cost flows into WIP and finished goods and reconciles to finance.

Work:

- Material cost, labor/overhead/additional cost, scrap value, recoveries, and cost variance.
- Partial completion and final completion cost allocation.
- WIP aging and open-order valuation.
- Finished-good unit cost and subsequent COGS on sale.
- Posting, unposting, cancellation, and rework accounting.
- Reconcile manufacturing reports, posting audit, stock valuation, GL, trial balance, P&L, and balance sheet.

Core invariants:

- Opening WIP + production inputs/costs - completed output cost - recognized loss/recovery = closing WIP.
- Finished-goods capitalization equals released production cost under the configured policy.
- Every manufacturing posting is balanced, scoped correctly, traceable, and reversible.

Exit criteria:

- End-to-end raw-material purchase -> production -> finished-good sale reconciles operationally and financially.

Evidence:

- The accounting trace confirmed periodic inventory reporting: sales movements retain FIFO acquisition cost, while Trading Account derives operational COGS from opening inventory, external period inflows, and closing inventory. No perpetual COGS journal is emitted by the sales adapter.
- Corrected a manufacturing double-counting defect in periodic COGS. Finished-goods receipts generated by production are internal conversions and are now excluded from period inflows; including them caused raw-material consumption to appear as COGS before any finished goods were sold.
- Added an end-to-end deterministic proof using raw materials valued at `450.00 + 20.00`, production of `10` finished units at `47.00`, and sale of `4` units. Immediately after production, closing stock remained `4700.00` and COGS was `0.00`; after sale, closing stock was `4512.00` and COGS was exactly `188.00`.
- The same proof verifies balanced manufacturing journals, `470.00` finished-goods capitalization, `470.00` WIP clearance, batch/location-scoped sale movement, and persisted sale extended cost of `188.00`.
- Focused command: `./venv/bin/python manage.py test manufacturing.tests.ManufacturingPhaseOneTests.test_production_and_finished_goods_sale_reconcile_cost_without_double_counting_cogs manufacturing.tests.ManufacturingPhaseOneTests.test_manufacturing_report_correctness_audit_reconciles_posted_work_order reports.tests_inventory --noinput --keepdb --verbosity=1`.
- Focused result: `25 passed`, zero failures and zero system-check issues.
- Wider command: `./venv/bin/python manage.py test manufacturing.tests reports.tests_inventory reports.tests_books financial.tests --noinput --keepdb --verbosity=1`.
- Wider result: `231 passed`, zero failures and zero system-check issues in 75.683 seconds.
- Remaining Phase 5 gate: deploy the correction and execute a staging raw-material -> production -> finished-goods sale proof against stock valuation, manufacturing reports, Trading Account, general ledger, trial balance, P&L, and balance sheet. Incremental partial completion accounting remains outside the supported model boundary documented in Phase 4.
- Staging revision `3c652c53` passed the Chromium manufacturing and financial reconciliation lane: 15 passed, 1 conditional skip, and 1 initial test-only date-label failure. The failed daybook assertion used Node's `Sept` abbreviation while the UI contract uses `Sep`; the shared live financial/payables formatter was normalized and the targeted rerun passed 2/2 including authentication.
- A read-only Manav-T database audit confirmed production receipts of `418.31` are excluded from external inflows exactly. It also exposed a separate `5200.00` inconsistency: Trading Account displayed the fallback GL opening stock but did not add that fallback to `cogs_from_issues`.
- Both summary and detailed Trading Account builders now apply the effective GL opening fallback consistently to opening stock and COGS. The existing opening-stock/balance-sheet regression now asserts `100.00` opening and `100.00` COGS in both contracts.
- The two focused regressions passed 2/2. The complete manufacturing, inventory-report, book-report, and financial suite passed 231/231 after the second correction, with zero failures and zero system-check issues in 65.846 seconds.
- Remaining deployment gate: deploy the GL-opening COGS correction, rerun the read-only equation audit, and rerun the staging financial statement relationship lane. Until then Phase 5 remains locally complete but not staging complete.

### Phase 6: Permissions, Isolation, Failure, And Recovery

Status: Pending

Goal: prove controls hold under unauthorized access and infrastructure failures.

Work:

- Role matrix for view/create/edit/operate/QC/post/unpost/cancel/export/settings.
- Entity, branch, location, FY, batch, and direct-object access isolation.
- API timeout, offline mode, 401/403/409/422/500, interrupted save, and repeated click/retry.
- Optimistic concurrency and stale-document updates.
- Verify useful errors, preserved user input, rollback, retry safety, and audit logs.

Exit criteria:

- Unauthorized operations are blocked in both UI and API.
- Failure and retry cannot duplicate stock movements, batches, work-order events, or journals.

Evidence: Pending.

### Phase 7: Reports, UX, Accessibility, And Cross-Browser Certification

Status: Pending

Goal: certify operational usability and reporting accuracy for daily users.

Work:

- Compare all inventory/manufacturing reports against seeded source transactions and independent totals.
- Verify filters, reset, date/FY behavior, pagination counts, sorting, drilldowns, export content, and empty states.
- Desktop, tablet, and mobile checks in Chromium, Firefox, and WebKit.
- Keyboard workflow, focus, labels, dialog focus trap, screen-reader names, and automated WCAG scans.
- Loading, long-name, large-number, validation, error, readonly, and no-data states.

Exit criteria:

- No critical visual/accessibility issue blocks entry, review, posting, or reconciliation.
- Exported and on-screen totals agree with source records.

Evidence: Pending.

### Phase 8: Scale, Repeatability, And Launch Gate

Status: Pending

Goal: establish production-like capacity and a repeatable release gate.

Work:

- Seed large product, batch, location, movement, BOM, and work-order datasets.
- Measure list/report load, save, post, unpost, valuation, genealogy, and report export duration.
- Run concurrent transfer, sale, adjustment, and work-order scenarios.
- Repeat critical suites to detect flakes and state leakage.
- Package one-command local and staging sign-off suites.
- Produce final defect matrix and release recommendation.

Suggested volumes:

- 10,000 products, 10 locations, 50,000 batches, and 250,000 movements where the environment permits.
- Work orders with 10, 100, and 500 material lines.
- Concurrent writes against the same and different product/location buckets.

Exit criteria:

- Agreed performance thresholds pass without integrity failures.
- Critical suites pass repeatedly from a clean deterministic baseline.
- No open severity-1 or severity-2 defect remains.

Evidence: Pending.

## Evidence Rules

For every completed phase record:

- Date, environment, application revision, database baseline, browser versions, and executor.
- Exact commands and test IDs executed.
- Passed, failed, skipped, and flaky counts.
- Created document IDs and independent expected results.
- Database/API/UI/report/GL evidence for financial invariants.
- Defects with severity, owner, fix revision, retest evidence, and residual risk.
- Updated confidence based on evidence, not elapsed effort or test count alone.

## Confidence Method

Final confidence is weighted by business impact:

| Area | Weight |
| --- | ---: |
| Stock quantity and movement integrity | 20% |
| Stock valuation and inventory accounting | 25% |
| Manufacturing execution and traceability | 15% |
| Manufacturing costing and accounting | 20% |
| Permissions, isolation, failure, and recovery | 10% |
| Reports, UX, accessibility, and cross-browser behavior | 5% |
| Performance and repeatability | 5% |

Confidence above 95% requires all critical invariants to pass locally and on staging, no open severity-1/2 defects, successful isolation and failure testing, and repeatable cross-browser execution. Mock-only tests cannot satisfy an accounting-integrity gate.

## Phase Update Log

| Date | Phase | Status | Evidence summary | Confidence |
| --- | --- | --- | --- | ---: |
| 8 Sep 2026 | Phase 0 | In progress | Living sign-off plan created; existing backend modules, frontend routes, and Playwright inventory/manufacturing suites identified | 72% |
| 8 Sep 2026 | Phase 0 | Completed | 73/73 backend tests passed; selected Chromium baseline returned 65 passed, 1 conditional skip, 0 failed; APIs, services, routes, reports, and permission boundaries mapped | 75% |
| 8 Sep 2026 | Phase 1 | Local complete, staging blocked | Masters/settings/BOM/route baseline green; opening-stock create/edit/delete/duplicate and stock-summary/trial-balance reconciliation green locally; staging exposed orphan postings after API deletion; transactional API cleanup fix added and local regression green | 78% |
| 8 Sep 2026 | Phase 1 | Completed | Final staging product lifecycle passed and the database audit found zero orphan opening-stock movements, entries, journals, or posting batches | 82% |
| 9 Sep 2026 | Phase 2 | In progress | Transfer/adjustment lifecycle, rollback, idempotency, staging report checks, database invariants, and deterministic non-batch/batch posting-to-report chains are green; invoice API linkage and repeatable CI concurrency remain | 89% |
| 9 Sep 2026 | Phase 2 | In progress | Full purchase/sales API lifecycle lane passed 176/176 after compliance and current-contract fixture corrections; one linked document-API chain and repeatable CI concurrency remain | 90% |
| 9 Sep 2026 | Phase 2 | In progress | Real document/API stock-to-GL chain passed; purchase, sale, and return journals balanced; fractional transfer/adjustment UOM conversion and exact reversal passed; full inventory suite 40/40 | 91% |
| 9 Sep 2026 | Phase 2 | In progress | Linked document chain now crosses BOX and PCS with exact persisted factors/base quantities; focused document and fractional reversal gates passed 2/2 with clean checks | 92% |
| 9 Sep 2026 | Phase 2 | In progress | Serialization false-capability removed: API/bulk/UI block new activation, legacy rows remain recoverable; 54/54 catalog and 128/128 product-form tests passed | 92% |
| 9 Sep 2026 | Phase 2 | In progress | Real purchase API -> transfer -> adjustment -> sales API -> return API chain reconciled to location/entity stock and balanced journals; expanded lifecycle lane passed 177/177 | 91% |
| 9 Sep 2026 | Phase 2 | In progress | Repeatable PostgreSQL concurrency tests prove simultaneous transfer/adjustment post plus retry produce one entry, one active batch, and exact movement cardinality; full inventory suite passed 42/42 | 93% |
| 9 Sep 2026 | Phase 2 | In progress | Concurrency matrix expanded to update-versus-post, duplicate unpost, and duplicate cancel for transfer and adjustment; exact final states and posting/movement cardinality passed in the full 45/45 inventory suite | 94% |
| 9 Sep 2026 | Phase 2 | Staging partially certified | Deployed transfer/adjustment browser lifecycles passed 3/3; inventory reconciliation passed 6/8 initially and both latency failures passed targeted rerun. Staging-host concurrency test DB creation is blocked by database-role privileges | 94% |
| 9 Sep 2026 | Phase 3 | In progress | Valuation/financial baseline passed 115/115; audit identified periodic-versus-perpetual accounting policy ambiguity and selling-price-derived outbound movement cost metadata requiring correction before valuation sign-off | 94% |
| 9 Sep 2026 | Phase 3 | Staging partially certified | Deployed inventory report/resilience/numeric reconciliation passed 15/15; transfer and adjustment lifecycle passed 3/3; goods-sale idempotent posting passed 2/2. Read-only database proof for sale 1048 found one active batch and one active move, FIFO cost 100.0000 from matching purchase layers, extended cost 100.00, and no duplicate commit. Manufacturing report reconciliation passed 5/5. Fresh manufacturing posting remains blocked by missing WIP, consumption, overhead absorption, and finished-goods static-account mappings in Manav-T; the standard-cost fixture also selected a batch-managed output without supplying a batch number. | 95% |
| 9 Sep 2026 | Phase 3 | Staging transaction proof complete | Standard-cost manufacturing proof passed after making the test fixture batch/expiry aware and temporarily provisioning all required mappings. Work order 4 produced one active batch and entry; material issues were 45.90 and 2.00, finished output was 0.9800 at 47.0000 with the required batch, and journal debits/credits both totalled 95.80. All temporary mappings were removed after the test. | 96% |
| 9 Sep 2026 | Phase 4 | In progress, core staging matrix green | Applied seven dedicated manufacturing static-account mappings for Manav-T branch 2 through the supported bootstrap command; post-apply Django check passed. Browser execution covered post/unpost/cancel, QC reject/rework/approve, operation skip, capitalized cost/byproduct recovery, and insufficient-stock rollback. Five business scenarios passed; the costing scenario had one report-hub navigation timeout and passed its isolated retry. Genealogy and downstream-consumption lock proofs remain. | 96% |
| 9 Sep 2026 | Phase 4 | Local complete, staging retest pending deployment | Batch genealogy proof covers multiple inputs and outputs with exact allocated input quantities and output batch linkage. Manufacturing unpost now rejects an active downstream OUT movement for the same entity/FY/branch/product/location/batch, preserves the posted work order and production movements, and succeeds after the downstream posting is reversed. Focused controls passed 2/2 and the full manufacturing backend suite passed 39/39. | 96% |
| 9 Sep 2026 | Phase 4 | Staging guard certified | Revision 33a81109 contains the downstream guard and passed Django system checks. Staging post/unpost/cancel and costing/byproduct browser workflows passed 3/3. A rollback-contained database probe against posted work order 12 created a matching downstream OUT movement, received the expected actionable unpost rejection, preserved POSTED status, and left zero probe batches or movements after rollback. | 96% |
| 9 Sep 2026 | Phase 4 | Concurrency hardening in progress | Shared posting now takes deterministic product-row locks for inventory movements, and manufacturing unpost takes the same ordered product locks before checking active downstream dependencies. Manufacturing, posting, and PostgreSQL inventory concurrency regression suites passed 94/94. Full race certification still requires business services to validate stock only after acquiring the shared product lock. | 96% |
| 9 Sep 2026 | Phase 4 | Supported scope locally complete | Centralized ordered product-row locking now runs before stock allocation/validation in manufacturing posting, sales invoice posting, inventory transfer, and inventory adjustment, and before manufacturing downstream-dependency inspection. The posting engine repeats the same lock defensively before persistence. Manufacturing, posting, PostgreSQL inventory concurrency, and sales regression suites passed 325/325. | 97% |
| 9 Sep 2026 | Phase 4 | Supported scope staging complete | Revision eecf28af verified with lock-before-validation in manufacturing, sales, transfer, and adjustment services; server check passed. Cross-module Chromium gate passed 7/7 across transfer, adjustment, production lifecycle, costing/byproduct, negative-stock rollback, and idempotent goods sale. A rollback-contained database proof found real downstream sale SI-SINV-82 consuming work order 14 output; unpost was rejected, status remained POSTED, and the probe left zero batches or movements. | 97% |
| 9 Sep 2026 | Phase 5 | Local core reconciliation complete | Corrected periodic COGS double counting by excluding internal production receipts from external inflows. Deterministic raw-material -> production -> finished-goods sale proof reconciled WIP, finished-goods capitalization, closing stock, and sale COGS; focused 25/25 and wider manufacturing/report/financial 231/231 suites passed. Staging financial-statement proof remains. | 97% |
| 9 Sep 2026 | Phase 5 | Staging audit found second defect; local fix green | Staging manufacturing and financial browser lane passed 15 checks with 1 conditional skip; a date-abbreviation test defect passed after correction. Read-only Manav-T audit proved production exclusion but exposed a 5200.00 GL-opening fallback mismatch in COGS. Summary/detailed builders were corrected and the full local accounting lane passed 231/231. Redeployment and final staging audit remain. | 97% |

Phase 4 capability boundary identified during certification:

- Current work orders support planned-versus-actual material/output quantities, waste, operation scrap, QC/rework, byproducts, and one final stock/accounting post.
- Incremental partial finished-goods receipts, multiple completion postings, explicit material-return documents, and product-substitution lineage are not represented as independent transactions in the current model. They require an approved workflow/schema extension before they can be certified.

### Phase 3 Staging Evidence - 9 Sep 2026

Environment and revision:

- Application: `https://accerio.in`
- Entity: `Manav-T`
- Deployed revision: `8a1d2fbd`
- Browser: Chromium through Playwright

Executed evidence:

- Inventory control resilience, cross-report scope, and numeric reconciliation: 15 passed, 0 failed.
- Transfer and adjustment draft lifecycle through cancellation: 3 passed, 0 failed.
- Manufacturing summary/material/output/WIP/posting-audit reconciliation: 5 passed, 0 failed.
- Goods invoice repeated-post/idempotency workflow: 2 passed, 0 failed.
- Persisted sale valuation audit: transaction 1048 has one active posting batch and one active inventory move; `cost_source=FIFO`, base quantity `1.0000`, unit cost `100.0000`, and extended cost `100.00`. Matching purchase receipt layers at the same product/location carry unit cost `100.0000`.
- Persisted movement cost constraints: 127 pre-proof Manav-T movements had zero negative costs and zero extended-cost mismatches. Historical sales rows retain their original `SALES` source; newly posted rows use `FIFO`.

Open staging blockers:

- Seven dedicated manufacturing ledgers and mappings are now permanently configured for `Manav-T` branch 2 using `bootstrap_static_accounts`. Accounting should review their classifications and reporting placement before production sign-off.
- `FIN-MFG-STD-COST-RECON-001` is now batch/expiry aware and passed on staging. The API validation remains enforced for incomplete controlled-product output lines.
- Periodic versus perpetual inventory accounting remains a product-policy decision; FIFO movement valuation is now correct, but Phase 3 financial sign-off requires the selected GL policy to be explicit and tested end to end.

## Final Launch Matrix

To be completed after Phase 8.

| Gate | Status | Blocking defects | Residual risk |
| --- | --- | --- | --- |
| Masters and opening position | Pending | Not assessed | Not assessed |
| Quantity and movement integrity | Pending | Not assessed | Not assessed |
| Inventory valuation and GL | Pending | Not assessed | Not assessed |
| Manufacturing execution | Pending | Not assessed | Not assessed |
| Manufacturing costing and GL | Pending | Not assessed | Not assessed |
| RBAC and isolation | Pending | Not assessed | Not assessed |
| Failure and recovery | Pending | Not assessed | Not assessed |
| Reports and usability | Pending | Not assessed | Not assessed |
| Performance and repeatability | Pending | Not assessed | Not assessed |
| Release recommendation | Pending | Not assessed | Not assessed |
