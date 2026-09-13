# RBAC Action Contract Hardening

Date: 13 September 2026

## Objective

Enforce tenant, entity, financial-year, branch, feature, and action permissions independently at the API boundary. UI visibility is supporting behavior; direct API denial is the release authority.

## Phase Status

| Phase | Scope | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Receivables scope and permissions | Complete | 11 API authorization contracts and 13 receivables business tests pass |
| 2 | Report view/export/print separation | Complete | Sales/receivables 50, Payables 99, Inventory 26, and Assets 81 tests pass |
| 3 | Sales AR and GST lifecycle separation | Complete | 339 sales lifecycle, compliance, AR, and contract tests pass |
| 4 | Frontend menu and action alignment | Complete | TypeScript passes; 429 focused Angular component tests pass |
| 5 | Application-wide RBAC contract matrix | Complete | Reports, bulk actions, master CRUD, account children, barcode output, custom fields, and invoice-import boundaries are enforced |
| 6 | Browser certification | Complete | Provisioned-role action, responsive, mobile-navigation, and WCAG journeys pass Chromium, Firefox, and WebKit |
| 7 | Launch sign-off | Complete | 95% scoped confidence; go for staging and conditional production recommendation |

## Phase 1 Coverage

- Tenant membership is checked before report data is built.
- Financial years and branches must belong to the requested entity.
- Branch-restricted users cannot request an unauthorized branch.
- Customer Outstanding, Receivable Aging, Aging Detail, Open Items, and Collections History require their exact view permissions.
- Overdue Customers, Credit Exposure, and Receivables Exceptions require their dedicated view permissions.
- View permission does not grant export permission.
- Export links and capability flags are omitted for view-only users.
- Direct CSV/export requests require the corresponding export permission.
- Reporting subscription entitlement is enforced through the shared scope guard.

## Verification

Command:

```text
./venv/bin/python manage.py test reports.tests_receivables_api_permissions reports.tests_receivables reports.tests_sales_register --keepdb --noinput --verbosity=1
```

Result: 50 tests passed. Django system checks and `git diff --check` passed.

## Phase 2 Coverage

- Sales Register view access no longer implies export access.
- Payables view-only users receive filtered metadata and no export or print actions.
- Every direct Payables export family requires `reports.payables.export` in addition to its configured report-view permission.
- Inventory now has an explicit `reports.inventory.export` capability shared by all 11 report families.
- Inventory file and print routes enforce export independently from each report's exact view permission.
- Asset reports enforce their existing per-report view and export permissions, including direct file and print routes.
- Legacy entity-owner access remains compatible where no explicit RBAC assignment exists; once roles are assigned, their restrictions are authoritative.

Verification:

```text
./venv/bin/python manage.py test reports.tests_payables --keepdb --verbosity=1
./venv/bin/python manage.py test reports.tests_inventory --keepdb --verbosity=1
./venv/bin/python manage.py test assets.tests --keepdb --verbosity=1
```

Result: 206 Phase 2 tests passed across Payables, Inventory, and Assets. The earlier 50 Sales/Receivables tests also pass.

## Phase 3 Coverage

- Sales AR view, manage, and export are independent API permissions.
- View-only users do not receive customer-statement export URLs or enabled export actions.
- Direct customer-statement export requests require `sales.ar.export` in addition to AR view access.
- IRN cancellation requires `sales.compliance.cancel_irn`; invoice update/edit access is not accepted as a substitute.
- E-way bill cancellation requires `sales.compliance.cancel_eway`; invoice update/edit access is not accepted as a substitute.
- Existing sales update, post, and unpost endpoints continue to enforce their exact lifecycle permissions.
- A data migration creates and grants the new AR permissions to the standard entity administration roles.

Verification:

```text
./venv/bin/python manage.py test sales.tests sales.tests_e2e_api sales.tests_invoice_contract_alignment --keepdb --verbosity=1
```

Result: 339 tests passed. Django system checks reported no issues and `git diff --check` passed.

## Phase 4 Coverage

- Customer Statement export and print controls now follow backend `actions` metadata per format.
- A denied Customer Statement export is stopped locally before issuing an API request.
- IRN and e-way cancellation controls require their exact frontend permission as well as a valid backend lifecycle flag.
- Sales Register, Receivables, Payables, Inventory, and Asset report controls were audited for backend-provided export URLs or available-format metadata.
- Receivables metadata-loading tests now assert the branch argument, preserving branch-aware report scope.
- Export icon buttons added in this phase have explicit accessible names.

Verification:

```text
npm run typecheck
ng test --configuration=ci --include=<customer-statement-and-sales-compliance-specs>
ng test --configuration=ci --include=<sales-receivables-payables-inventory-assets-specs>
```

Result: TypeScript passed, 115 Customer Statement/compliance tests passed, and 314 cross-report component tests passed.

## Next Execution Target

Check in and deploy the backend, frontend, and Playwright changes, apply RBAC migrations `0153` through `0159`, then execute the staging role smoke and concurrent-session permission-change checks listed in the residual launch gates.

## Phase 5 Coverage To Date

- Trial Balance, Ledger Book, Ledger Summary, Profit and Loss, Balance Sheet, and Trading Account separate view from export/print at the API boundary.
- Day Book, Cash Book, and Posting Detail file/print routes require their dedicated export permissions.
- View-only report responses omit export URLs, available formats, and print capability metadata.
- Frontend report print controls no longer fall back to unrestricted browser printing when protected print export is unavailable.
- Product, HSN/SAC, Account, TCS Section, TCS Rule, and TCS Config bulk operations now distinguish template/view, export, and import permissions.
- Bulk validate and commit share the explicit import permission; error-file downloads require the same import authority.
- Bulk export/import controls are omitted from the corresponding Angular screens when the user lacks the exact action permission.
- RBAC migration `0159_add_bulk_master_action_permissions` creates 12 action permissions, links them to their operational menus, and grants them to standard entity administration roles.
- Direct API negative tests prove that view-only users cannot export or initiate bulk import validation.
- Product, category, brand, UOM, HSN/SAC, price-list, and product-attribute APIs enforce method-specific view/create/update/delete permissions.
- Product child APIs, including GST rates, UOM conversions, opening stock, prices, planning, attributes, and images, inherit the product action contract.
- Product barcode records and label templates enforce product view/create/update/delete actions; PDF generation requires product export authority.
- Account type, account head, ledger, and account APIs enforce method-specific view/create/update/delete permissions and deny cross-entity detail access before serialization or mutation.
- Account contacts and shipping addresses are entity-scoped. Reads require account view, additions require account create or update, and mutations require account update. Parent account reassignment is rejected.
- Invoice custom-field management requires `admin.invoice_custom_fields.view` or `admin.invoice_custom_fields.update` as appropriate. Operational invoice users can read effective fields and party defaults only with the matching sales or purchase invoice view permission.
- Custom-field subentities, target accounts, definitions, and defaults are validated against the same entity before access or persistence.
- Legacy entity owners without an RBAC assignment retain compatibility; as soon as an assignment exists, its explicit permissions are authoritative.
- Invoice-import templates and job reads require document view, upload/profile creation and source error workbooks require create, review requires update, and commit requires post.
- Ordinary Angular master screens hide and locally guard create/update/delete/export actions using the same exact permission codes enforced by the API.

Phase 5 verification:

```text
./venv/bin/python manage.py test withholding.tests reports.gstr1.tests.test_gstr1_report reports.gstr3b.tests.test_gstr3b_summary reports.gstr9.tests.test_gstr9_scaffold_api reports.tests_gst_reconciliation reports.tests_gst_exception_dashboard reports.tests_financial_api_permissions reports.tests_book_api_permissions --keepdb --noinput --verbosity=1
./venv/bin/python manage.py test financial.tests.FinancialAccountsBulkCoverageTests catalog.tests withholding.tests --keepdb --noinput --verbosity=1
./venv/bin/python manage.py test financial.tests catalog.tests --keepdb --noinput --verbosity=1
npm run typecheck
ng test --configuration=ci --include=<financial-and-book-report-specs>
ng test --configuration=ci --include=<account-product-hsn-and-tcs-bulk-specs>
```

Results: 259 consolidated report/compliance backend tests passed, 199 bulk-master backend tests passed, and the final catalog/financial run passed 188 tests. Frontend evidence includes 230 financial/book tests, 213 bulk-master tests, 130 product-form tests, and 45 account-workspace/custom-field tests. TypeScript compilation, Django system checks, and migration drift checks passed.

## Phase 6 Browser Risks

- Provisioned zero-permission and view-only users are denied protected routes and mutation APIs in Chromium.
- Product, account, barcode, and custom-field controls remain hidden for a provisioned view-only user; six direct API probes return `403`.
- The focused master action contract passes Chromium, Firefox, and WebKit.
- Foreign-entity context mutation and branch-external/entity-wide reads are denied in the provisioned Chromium matrix.
- Purchase operator, accountant, approver, and reporting roles receive only their assigned workflow actions.
- HRMS viewer and employee/manager role boundaries pass in the same provisioned matrix.
- Products, Accounts, Invoice Custom Fields, and Access Restricted pass page-level overflow checks at 1440x900, 834x1112, and 390x844.
- The same four restricted-role surfaces pass automated WCAG 2 A/AA and WCAG 2.1 A/AA scans at all three viewport sizes.
- Mobile navigation exposes the permitted Products, Accounts, and Invoice Custom Fields destinations through their real nested menu interactions.
- Navigation group buttons now expose their expanded state to assistive technology.
- Product filter selects now have explicit accessible names. Shared catalog active-sort contrast and shared master descriptive-copy contrast were corrected after the certification scan found them.

Phase 6 verification:

```text
playwright test tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --grep FIN-MASTER-RBAC-VIEW-001 --project=chromium --project=firefox --project=webkit --no-deps --workers=1 --reporter=line
playwright test tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --project=chromium --no-deps --workers=1 --reporter=line
playwright test tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --grep FIN-MASTER-RBAC-A11Y-001 --project=chromium --workers=1 --reporter=line
playwright test tests/p1/admin-restricted-rbac-provisioned.p1.spec.ts --grep FIN-MASTER-RBAC-A11Y-001 --project=firefox --project=webkit --workers=1 --reporter=line
npm run test:ci -- --include=src/app/component/catalog/products/product-list.component.spec.ts --include=src/app/component/financial-master/accounts/accounts.component.spec.ts --include=src/app/component/route/route.component.spec.ts
npm run typecheck
```

Results: Phase 6 is complete. The focused master contract passed in all three browsers, all 7 provisioned Chromium RBAC journeys passed, and the responsive/WCAG master certification passed in Chromium, Firefox, and WebKit. The certification covers 12 surface/viewport combinations per browser plus the nested mobile menu journey. Frontend follow-up verification passed 180 unit tests and TypeScript compilation. Firefox and WebKit authentication states were refreshed before certification.

## Phase 7 Launch Matrix

| Release invariant | Status | Evidence | Residual risk |
| --- | --- | --- | --- |
| Entity and branch isolation | Pass | Provisioned-role foreign-entity and branch denial journeys; scoped report API tests | Concurrent context switching is not load-tested in this phase |
| View versus create/update/delete | Pass | Ordinary master API contracts, hidden UI controls, and six direct `403` probes | Legacy owner fallback remains intentionally permissive when no assignment exists |
| View versus export/print/import | Pass | Financial, book, GST, TCS, purchase statutory, inventory, asset, receivables, and payables contracts | Staging must apply RBAC migrations `0153` through `0159` before smoke testing |
| Transaction lifecycle permissions | Pass | Purchase role matrix and sales create/update/post/unpost/compliance tests | A live role change during an already-open browser session needs concurrency coverage |
| Invoice-import workflow separation | Pass | Template/read, upload, review, commit, and error-workbook permissions are independently enforced | High-volume concurrent commits remain outside this RBAC-focused phase |
| Menu and route alignment | Pass | Zero-permission, view-only, direct-route, and nested mobile-menu journeys | Manual review is still required after staging menu migration deployment |
| Responsive restricted-role experience | Pass | Products, Accounts, Custom Fields, and Access Restricted at desktop, tablet, and mobile sizes | Device-specific browser chrome is not part of automated viewport emulation |
| Automated accessibility | Pass | WCAG 2/2.1 A/AA scans across 12 surface/viewport combinations in all three engines | Manual screen-reader announcement and reading-order review remains open |
| Frontend regression safety | Pass | 180 focused unit tests and TypeScript compilation | Full frontend suite should remain part of the deployment pipeline |
| Backend regression safety | Pass | Consolidated report, compliance, catalog, financial, sales, purchase, and withholding suites documented above | Full-project Django suite was not rerun as one monolithic command in this phase |

## Residual Launch Gates

1. Apply and verify migrations `0153` through `0159` on staging before testing assigned roles.
2. Run one staging smoke for zero-permission, view-only, operator, accountant, approver, and reporting users.
3. Verify role removal and permission changes in two concurrent sessions to confirm cache/session refresh behavior.
4. Complete manual VoiceOver or NVDA review for navigation state, denied-route guidance, tables, and dialogs.
5. Keep the legacy owner fallback documented and monitored; explicit RBAC assignments must remain authoritative once present.

## Release Recommendation

**RBAC/action-contract confidence: 95%.** This score applies only to the authorization, menu/action visibility, export/import separation, tenant isolation, and restricted-role presentation covered by this document. It is not a whole-application confidence score.

Recommendation: **go for staging deployment and sign-off; conditional go for production** after the residual launch gates above pass with no severity-1 or severity-2 findings. No open severity-1 or severity-2 defect is known in the locally certified scope.
