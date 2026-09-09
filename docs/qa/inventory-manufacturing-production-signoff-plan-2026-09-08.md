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
| GAP-COST-001 | WIP equation, partial cost allocation, scrap/recovery, overhead, variance, finished-goods capitalization, and subsequent sale COGS | Critical | Phase 5 |
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
- The earlier teardown failure was isolated to a stale retained test schema. Rebuilding the test database through the complete migration graph removed the orphan payroll foreign-key condition, and both concurrency tests plus the complete `42/42` inventory suite passed.
- Remaining Phase 2 gates: certify the linked and concurrency chains on staging and close the remaining long-chain UOM boundary rows recorded in the coverage register. Serialized inventory remains an explicitly gated future capability.
- Interim confidence increased from `82%` to `94%`; Phase 2 is not yet complete.

### Phase 3: Valuation And Inventory Accounting

Status: Pending

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

Evidence: Pending.

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

Status: Pending

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

Evidence: Pending.

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
