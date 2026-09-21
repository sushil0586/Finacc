# Canonical Subscription, Role, Menu, and Permission Access Plan

Date: 2026-09-21

Status: Locked for implementation until final launch signoff.

## Objective

Make entity onboarding deterministic and production-safe. A newly onboarded customer should receive the correct menus, roles, permissions, and route access automatically from the subscription selected in Platform Admin.

This replaces legacy menu repair behavior with a canonical access contract.

## Core Rules

Subscription decides which modules exist for the customer.

Role decides what the user can see and do inside the subscribed modules.

Menu catalog decides where pages appear.

Permission codes decide whether pages and actions are allowed.

Menus must be visible only when all of these are true:

1. The subscription includes the feature.
2. The role has the menu visibility permission.
3. The page route permission is active.

Entity Super Admin receives all permissions allowed by the customer's subscription, not every system permission globally.

## Subscription Packages

### Basic Accounting

Includes:

- Dashboard
- Sales
- Purchase
- Accounts
- Catalog
- Core financial reports

### Professional Accounting

Includes Basic Accounting plus:

- Payables
- Receivables
- Assets
- Advanced financial and operational reports

### Compliance

Includes:

- GST Compliance Center
- GSTR-1
- GSTR-3B
- GSTR-1 vs GSTR-3B Reconciliation
- GSTR-9
- GST Exception Dashboard
- GST Portal
- ITC / 2B
- E-Invoice / E-Way
- GST-TDS
- TDS
- TCS

### Treasury

Includes:

- Treasury Setup
- Treasury Execution
- Payment Batches
- Bank Reconciliation
- Cheque Books
- Cash Forecast

### People

Includes:

- HRMS
- Payroll

### Enterprise

Includes all available modules.

## Default Entity Roles

Every onboarded entity gets:

- Entity Super Admin
- Admin
- Accounts Manager
- Sales User
- Purchase User
- Financial Report Viewer

Professional Accounting adds:

- Payables User
- Receivables User
- Asset Manager

Compliance adds:

- Compliance User
- GST Reviewer

Treasury adds:

- Treasury User
- Treasury Approver

People adds:

- HRMS User
- HRMS Approver
- Payroll User
- Payroll Approver
- Payroll Finance Manager

## Canonical Menu Hierarchy

Only subscribed and role-visible sections should appear.

```text
Dashboard
  Home
  Analytics
  Dashboard

Purchase
  Purchase Invoices
  Purchase Credit Notes
  Purchase Orders / GRN where enabled
  Purchase Compliance

Sales
  Sales Invoices
  Sales Credit Notes
  Sales Orders / Dispatch where enabled
  E-Invoice / E-Way actions

Accounts
  Ledgers
  Vouchers
  Trial Balance
  Posting Setup
  Year-End Close

Catalog
  Products
  Product Categories
  Brands
  UOM
  HSN/SAC
  Price Lists

Assets
  Asset Registry
  Depreciation
  Asset Settings

Treasury
  Treasury Setup
  Treasury Execution
  Payment Batches
  Bank Reconciliation
  Cheque Books
  Cash Forecast

Compliance
  GST Operations
  TDS
  TCS

Reports
  Financial Reports
  Payables Reports
  Receivables Reports
  Sales Reports
  Purchase Reports
  Inventory Reports
  Asset Reports
  Compliance Reports
    GST Compliance Center
    GST Report
    GSTR-1
    GSTR-3B
    GSTR-1 vs GSTR-3B
    GSTR-9
    GST Exceptions
    GST Portal
    ITC / 2B
    GST-TDS
    TCS

Admin
  Users
  Roles
  Menu Access
  Static Account Settings
  Business Settings

Payroll
  Payroll Dashboard
  Payroll Runs
  Salary Structures
  Components
  Statutory Setup
  Payroll Reports

HRMS
  Organization Units
  Employees
  Employment Contracts
  Shifts
  Attendance
  Leave
  Holiday Calendars
  Onboarding
```

## Legacy Policy

Do not preserve legacy menu accidents during the final implementation.

Remove or deactivate:

- Old `masters` tree
- Old top-level `inventory` tree
- Duplicate `reports > reports` branches
- Duplicate route aliases that point to the same screen

Preserve current canonical pages:

- Catalog
- Reports > Inventory
- Assets
- Treasury
- Compliance
- HRMS
- Payroll

## Implementation Phases

### Phase 1: Access Matrix

Create the canonical matrix:

```text
subscription -> module -> menu -> route -> permission -> default roles
```

No DB mutation in this phase.

## Phase 1 Access Matrix

### Subscription Feature Codes

These feature flags are the product contract. They should be present in
`SubscriptionLimitCodes`, `LIMIT_CATALOG`, `FEATURE_MESSAGE_MAP`, route metadata,
API view mixins, and menu metadata.

| Feature code | Purpose | Notes |
| --- | --- | --- |
| `feature_financial` | Core accounting, vouchers, ledgers, fiscal setup, dashboard, trial balance, P&L, balance sheet | Base accounting feature. |
| `feature_sales` | Sales invoices, sales credit/debit notes, sales settings, customer-facing sales workflow | Does not include advanced receivables reports unless bundled. |
| `feature_purchase` | Purchase invoices, purchase credit/debit notes, purchase settings, vendor purchase workflow | Does not include advanced payables reports unless bundled. |
| `feature_catalog` | Products, categories, brands, UOM, HSN/SAC, price lists | May be included with sales/purchase/inventory bundles. |
| `feature_inventory` | Stock locations, transfers, adjustments, stock reporting, inventory controls | Replaces old top-level legacy inventory menu. |
| `feature_manufacturing` | BOM, work orders, routes, manufacturing reports | Separate from inventory so non-manufacturing customers can hide it. |
| `feature_assets` | Fixed asset register, depreciation, asset reports, asset settings | Professional accounting and Enterprise. |
| `feature_reporting` | Financial reports, books, registers, operational reports | Core reports stay with financial; advanced hubs use this feature. |
| `feature_payables` | Vendor outstanding, AP aging, settlement history, payables close pack, AP controls | Professional accounting and Enterprise. |
| `feature_receivables` | Customer outstanding, AR aging, collections, customer statements, receivables hub | Professional accounting and Enterprise. |
| `feature_treasury` | Treasury setup, payment batches, instruments, bank reconciliation, cash forecast, cheque books | Separate from financial. |
| `feature_compliance` | GST/TDS/TCS compliance operations and compliance reports | Umbrella compliance feature. |
| `feature_gst_compliance` | GST Compliance Center, GSTR-1, GSTR-3B, GSTR-9, ITC/2B, GST Portal, GST Exceptions | Can be enabled independently under Compliance. |
| `feature_hrms` | Organization units, employees, contracts, shifts, leave, attendance, holiday calendars | Separate from payroll. |
| `feature_payroll` | Payroll setup, salary structures, payroll runs, statutory payroll, payroll reports | Depends on HRMS data but can be licensed separately if required. |
| `feature_rbac` | Users, roles, menu access, permissions | Included in every paid operational plan. |

### Subscription Package Matrix

| Package | Included feature codes |
| --- | --- |
| Basic Accounting | `feature_financial`, `feature_sales`, `feature_purchase`, `feature_catalog`, `feature_reporting`, `feature_rbac` |
| Professional Accounting | Basic Accounting plus `feature_payables`, `feature_receivables`, `feature_assets`, `feature_inventory` |
| Compliance | `feature_compliance`, `feature_gst_compliance`, `feature_reporting` |
| Treasury | `feature_treasury`, `feature_financial`, `feature_payables`, `feature_receivables` |
| People | `feature_hrms`, `feature_payroll`, `feature_rbac` |
| Enterprise | All feature codes |

Implementation note: a customer may subscribe to one package or a combination of
packages. The effective feature set is the union of all active package limits.

### Default Role Matrix

| Role code | Created when | Purpose |
| --- | --- | --- |
| `entity.super_admin` | Every entity | All subscribed permissions for the entity. Never all global permissions. |
| `admin` | Every entity | Setup access for subscribed modules, except destructive/system-only operations. |
| `accounts_manager` | Basic Accounting+ | Core accounting, vouchers, ledgers, posting review, financial reports. |
| `sales_user` | Basic Accounting+ | Sales document workflow and sales settings where permitted. |
| `purchase_user` | Basic Accounting+ | Purchase document workflow and purchase settings where permitted. |
| `financial_report_viewer` | Basic Accounting+ | Read-only financial reports. |
| `payables_user` | Professional Accounting+ | Vendor/AP reporting and payables review workflows. |
| `receivables_user` | Professional Accounting+ | Customer/AR reporting and receivables review workflows. |
| `asset_manager` | Professional Accounting+ | Asset master, depreciation, asset reports. |
| `inventory_user` | Professional Accounting+ when inventory enabled | Inventory locations, transfers, adjustments, stock reports. |
| `manufacturing_user` | Manufacturing enabled | BOM, work orders, routes, manufacturing reports. |
| `treasury_user` | Treasury enabled | Treasury execution, batches, instruments, reconciliation review. |
| `treasury_approver` | Treasury enabled | Payment batch approval and treasury control actions. |
| `compliance_user` | Compliance enabled | TDS/TCS/GST report access and compliance workspace review. |
| `gst_reviewer` | GST Compliance enabled | GST Compliance Center, reconciliation, evidence review. |
| `hrms_user` | HRMS enabled | HRMS operational maintenance. |
| `hrms_approver` | HRMS enabled | HRMS review and approval workflows. |
| `payroll_user` | Payroll enabled | Payroll setup and run preparation. |
| `payroll_approver` | Payroll enabled | Payroll approval and lock workflows. |
| `payroll_finance_manager` | Payroll enabled with financial | Payroll posting, payment handoff, accounting reconciliation. |

### Canonical Menu/Page Matrix

Routes listed here are menu targets. Legacy aliases may continue as redirects for
backward compatibility, but must not appear as separate menu entries.

| Main menu | Page / group | Canonical route | Feature | Primary permission | Default roles |
| --- | --- | --- | --- | --- | --- |
| Dashboard | Home | `/home` | `feature_financial` | `dashboard.home.view` | all subscribed operational roles |
| Dashboard | Analytics | `/dashboard-analytics` | `feature_reporting` | `dashboard.analytics.view` | super admin, admin, report viewers, managers |
| Purchase | Purchase Invoice | `/purchaseinvoice` | `feature_purchase` | `purchase.invoice.view` | purchase user, accounts manager, admin |
| Purchase | Purchase Service Invoice | `/purchaseserviceinvoice` | `feature_purchase` | `purchase.invoice.view` | purchase user, accounts manager, admin |
| Purchase | Purchase Credit Note | `/purchasecreditnoteinvoice` | `feature_purchase` | `purchase.credit_note.view` | purchase user, accounts manager, admin |
| Purchase | Purchase Debit Note | `/purchasedebitnoteinvoice` | `feature_purchase` | `purchase.debit_note.view` | purchase user, accounts manager, admin |
| Sales | Sales Invoice | `/saleinvoice` | `feature_sales` | `sales.invoice.view` | sales user, accounts manager, admin |
| Sales | Sales Service Invoice | `/saleserviceinvoice` | `feature_sales` | `sales.invoice.view` | sales user, accounts manager, admin |
| Sales | Sales Credit Note | `/salecreditnoteinvoice` | `feature_sales` | `sales.credit_note.view` | sales user, accounts manager, admin |
| Sales | Sales Debit Note | `/saledebitnoteinvoice` | `feature_sales` | `sales.debit_note.view` | sales user, accounts manager, admin |
| Sales | Bulk Print Center | `/sales-bulk-print-center` | `feature_sales` | `sales.invoice.view` | sales user, admin |
| Accounts | Journal Voucher | `/journalvoucher` | `feature_financial` | `voucher.journal.view` | accounts manager, admin |
| Accounts | Bank Voucher | `/bankvoucher` | `feature_financial` | `voucher.bank.view` | accounts manager, treasury user, admin |
| Accounts | Cash Voucher | `/cashvoucher` | `feature_financial` | `voucher.cash.view` | accounts manager, admin |
| Accounts | Receipt Voucher | `/receiptvoucher` | `feature_financial` | `voucher.receipt.view` | accounts manager, receivables user, admin |
| Accounts | Payment Voucher | `/paymentvoucher` | `feature_financial` | `voucher.payment.view` | accounts manager, payables user, treasury user, admin |
| Accounts | Account Types | `/financial-master/account-types` | `feature_financial` | `accounts.master.view` | accounts manager, admin |
| Accounts | Account Heads | `/financial-master/account-heads` | `feature_financial` | `accounts.master.view` | accounts manager, admin |
| Accounts | Ledgers | `/financial-master/ledgers` | `feature_financial` | `accounts.ledger.view` | accounts manager, admin |
| Accounts | Accounts | `/financial-master/accounts` | `feature_financial` | `accounts.account.view` | accounts manager, admin |
| Accounts | Static Account Settings | `/staticaccountsettings` | `feature_financial` | `posting.static_account_settings.view` | admin, accounts manager |
| Accounts | Capital Distribution Setup | `/capital-distribution-setup` | `feature_financial` | `capital_distribution.setup.view` | admin, accounts manager |
| Catalog | Products | `/catalogproducts` | `feature_catalog` | `catalog.product.view` | sales user, purchase user, inventory user, admin |
| Catalog | Product Categories | `/catalogproductcategories` | `feature_catalog` | `catalog.category.view` | admin, catalog/inventory users |
| Catalog | Brands | `/catalogbrands` | `feature_catalog` | `catalog.brand.view` | admin, catalog/inventory users |
| Catalog | UOM | `/cataloguoms` | `feature_catalog` | `catalog.uom.view` | admin, catalog/inventory users |
| Catalog | HSN/SAC | `/cataloghsnsac` | `feature_catalog` | `catalog.hsn_sac.view` | admin, catalog/inventory users, compliance user |
| Catalog | Price Lists | `/catalogpricelists` | `feature_catalog` | `catalog.price_list.view` | admin, sales user |
| Inventory | Stock Management | `/stockmanagement` | `feature_inventory` | `inventory.stock.view` | inventory user, admin |
| Inventory | Location Master | `/inventory-location-master` | `feature_inventory` | `inventory.location.view` | inventory user, admin |
| Inventory | Transfer Entry | `/inventory-transfer-entry` | `feature_inventory` | `inventory.transfer.view` | inventory user, admin |
| Inventory | Transfer List | `/inventory-transfer-list` | `feature_inventory` | `inventory.transfer.view` | inventory user, admin |
| Inventory | Adjustment Entry | `/inventory-adjustment-entry` | `feature_inventory` | `inventory.adjustment.view` | inventory user, admin |
| Inventory | Adjustment List | `/inventory-adjustment-list` | `feature_inventory` | `inventory.adjustment.view` | inventory user, admin |
| Manufacturing | Work Order Entry | `/productionorder` | `feature_manufacturing` | `manufacturing.workorder.view` | manufacturing user, admin |
| Manufacturing | Work Order List | `/manufacturing-work-order-list` | `feature_manufacturing` | `manufacturing.workorder.view` | manufacturing user, admin |
| Manufacturing | BOMs | `/manufacturing-boms` | `feature_manufacturing` | `manufacturing.bom.view` | manufacturing user, admin |
| Manufacturing | Routes | `/manufacturing-routes` | `feature_manufacturing` | `manufacturing.route.view` | manufacturing user, admin |
| Assets | Asset Dashboard | `/asset-dashboard` | `feature_assets` | `assets.asset_dashboard.view` | asset manager, admin |
| Assets | Asset Master | `/asset-master` | `feature_assets` | `assets.asset.view` | asset manager, admin |
| Assets | Asset Category Master | `/asset-category-master` | `feature_assets` | `assets.category.view` | asset manager, admin |
| Assets | Depreciation Run | `/depreciation-run` | `feature_assets` | `assets.depreciation_run.view` | asset manager, accounts manager, admin |
| Assets | Fixed Asset Register | `/fixed-asset-register` | `feature_assets` | `assets.fixed_asset_register.view` | asset manager, report viewer, admin |
| Assets | Asset Location and Custodian | `/asset-location-custodian` | `feature_assets` | `assets.asset_location_custodian.view` | asset manager, admin |
| Assets | Depreciation Schedule | `/depreciation-schedule` | `feature_assets` | `assets.depreciation_schedule.view` | asset manager, accounts manager, report viewer |
| Assets | Asset Events | `/asset-events` | `feature_assets` | `assets.asset_events.view` | asset manager, report viewer |
| Assets | Asset History | `/asset-history` | `feature_assets` | `assets.asset_history.view` | asset manager, report viewer |
| Treasury | Treasury Setup | `/treasury-setup` | `feature_treasury` | `treasury.setup.view` | treasury user, treasury approver, admin |
| Treasury | Treasury Execution | `/treasury-execution` | `feature_treasury` | `treasury.payment_batch.view` | treasury user, treasury approver, admin |
| Treasury | Treasury Instruments | `/treasury-instruments` | `feature_treasury` | `treasury.payment_batch.view` | treasury user, treasury approver, admin |
| Compliance | GST Reconciliation | `/gst-reconciliation` | `feature_gst_compliance` | `gst.reconciliation.view` | gst reviewer, compliance user, admin |
| Compliance | TCS Return 27EQ | `/tcsreturn27eq` | `feature_compliance` | `compliance.tcs_return_27eq.view` | compliance user, admin |
| Compliance | TCS Config | `/tcsconfig` | `feature_compliance` | `compliance.tcs_config.view` | compliance user, admin |
| Reports | Reports Hub | `/reports` | `feature_reporting` | `reports.financial_hub.view` | report viewer, managers, admin |
| Reports | Trial Balance | `/trialbalance` | `feature_reporting` | `reports.trial_balance.view` | report viewer, accounts manager, admin |
| Reports | Daybook | `/daybook` | `feature_reporting` | `reports.daybook.view` | report viewer, accounts manager, admin |
| Reports | Purchase Register | `/reports/payables/purchase-register` | `feature_reporting` | `reports.purchase_register.view` | purchase user, report viewer, admin |
| Reports | Sales Register | `/salesregister` | `feature_reporting` | `reports.sales_register.view` | sales user, report viewer, admin |
| Reports | Payables Hub | `/reports/payables` | `feature_payables` | `reports.payables.view` | payables user, accounts manager, admin |
| Reports | Vendor Outstanding | `/reports/payables/vendor_outstanding` | `feature_payables` | `reports.vendoroutstanding.view` | payables user, accounts manager, admin |
| Reports | AP Aging | `/reports/payables/ap_aging` | `feature_payables` | `reports.accountspayableaging.view` | payables user, accounts manager, admin |
| Reports | Vendor Ledger Statement | `/reports/payables/vendor_ledger_statement` | `feature_payables` | `reports.vendorledgerstatement.view` | payables user, accounts manager, admin |
| Reports | Receivables Hub | `/reports/receivables` | `feature_receivables` | `reports.financial_hub.receivables_hub.view` | receivables user, accounts manager, admin |
| Reports | Inventory Hub | `/reports/inventory` | `feature_inventory` | `reports.inventory.view` | inventory user, report viewer, admin |
| Reports | GST Compliance Center | `/reports/compliance/gst-compliance-center` | `feature_gst_compliance` | `reports.gst_compliance_center.view` | gst reviewer, compliance user, admin |
| Reports | GST Report / GSTR-1 | `/gstreport` | `feature_gst_compliance` | `reports.gst.view` | gst reviewer, compliance user, admin |
| Reports | GSTR-3B | `/gstr3breport` | `feature_gst_compliance` | `reports.gstr3b.view` | gst reviewer, compliance user, admin |
| Reports | GSTR-1 vs GSTR-3B | `/reports/gstr1-gstr3b-reconciliation` | `feature_gst_compliance` | `reports.gstr1_gstr3b_reconciliation.view` | gst reviewer, compliance user, admin |
| Reports | GSTR-9 | `/reports/gstr9` | `feature_gst_compliance` | `reports.gstr9.view` | gst reviewer, compliance user, admin |
| Reports | GST Exceptions | `/reports/gst-exception-dashboard` | `feature_gst_compliance` | `reports.gst_exception_dashboard.view` | gst reviewer, compliance user, admin |
| Admin | Business Settings | `/businesssettings` | `feature_financial` | `admin.business_settings.view` | admin |
| Admin | Users | `/user` | `feature_rbac` | `admin.user.view` | admin, super admin |
| Admin | Roles | `/rbacmanagement` | `feature_rbac` | `admin.role.view` | admin, super admin |
| Admin | Sales Settings | `/salessettings` | `feature_sales` | `sales.settings.view` | admin, sales manager |
| Admin | Purchase Settings | `/purchasesettings` | `feature_purchase` | `purchase.settings.view` | admin, purchase manager |
| Admin | Payment Settings | `/paymentsettings` | `feature_financial` | `voucher.payment_settings.view` | admin, accounts manager |
| Admin | Receipt Settings | `/receiptsettings` | `feature_financial` | `voucher.receipt_settings.view` | admin, accounts manager |
| Admin | Voucher Settings | `/vouchersettings` | `feature_financial` | `voucher.settings.view` | admin, accounts manager |
| Admin | Inventory Settings | `/inventory-ops-settings` | `feature_inventory` | `inventory.settings.view` | admin, inventory user |
| Admin | Manufacturing Settings | `/manufacturingsettings` | `feature_manufacturing` | `manufacturing.settings.view` | admin, manufacturing user |
| Payroll | Payroll Workspace | `/payroll` | `feature_payroll` | `payroll.run.view` | payroll user, payroll approver, payroll finance manager, admin |
| HRMS | HRMS pages | HRMS route group | `feature_hrms` | `hrms.*.view` | hrms user, hrms approver, admin |

### Routes That Must Not Be Separate Menu Items

The following route families are allowed for backward compatibility, redirects,
or direct workflow navigation, but should not create duplicate menu entries:

- Old compact aliases such as `/assetmaster`, `/assetcategorymaster`,
  `/depreciationrun`, `/financialmaster/*`.
- Duplicate sales/purchase charge-type aliases such as `/saleschargetypes` and
  `/purchasechargetypes` when canonical settings routes exist.
- Dynamic drilldown routes such as detail/edit pages, run-detail pages, and
  workspace child pages.
- Legacy trees under `masters` and old top-level `inventory`.
- Duplicate `Reports > Reports` nests.

### Required Code Changes After Phase 1

1. Add missing feature codes to `SubscriptionLimitCodes`, `LIMIT_CATALOG`, and
   `FEATURE_MESSAGE_MAP`.
2. Introduce a canonical access catalog, preferably a Python module such as
   `rbac/access_catalog.py`, so role templates and migrations use one source.
3. Update `RBACSeedService.seed_entity()` to derive subscribed features from the
   entity's customer subscription.
4. Grant `entity.super_admin` only the permission set allowed by subscribed
   features.
5. Create default role shells only for subscribed packages.
6. Replace broad prefix role templates with explicit canonical permission sets.
7. Add `feature_code`, `canonical_route`, `access_mode`, and `is_canonical` to
   `Menu.metadata` during catalog seeding.
8. Filter `EffectiveMenuService.menu_tree_for_user()` by subscribed features
   before returning the tree.
9. Align frontend route metadata and backend API mixins:
   - Treasury must use `feature_treasury`, not `feature_financial`.
   - GST compliance must use `feature_gst_compliance` or `feature_compliance`,
     not generic `feature_reporting`.
   - HRMS must use `feature_hrms`, not `feature_payroll`.
   - Manufacturing must use `feature_manufacturing`, not only
     `feature_inventory`.

### Phase 1 Definition of Done

- The matrix above is the authoritative product contract.
- Every new migration must seed from this contract or intentionally document a
  deviation.
- No migration should recreate old `masters`, old top-level `inventory`, or
  duplicate nested `reports` menus.
- No menu is considered valid unless it has:
  - one canonical route,
  - one feature code,
  - one visibility permission,
  - at least one subscribed role path.

### Phase 2: Canonical Menu Catalog

Create one source-of-truth menu catalog and remove legacy menu branches only when canonical equivalents exist.

### Phase 3: Permission Catalog

Create or repair all view/action permissions. Prefer one canonical view permission per screen.

### Phase 4: Role Templates

Create subscription-aware role templates for new entity onboarding.

### Phase 5: Subscription Gates

Map every feature/menu group to subscription feature codes.

### Phase 6: Onboarding Integration

Platform entity onboarding should:

1. Read selected subscription.
2. Seed canonical menus and permissions.
3. Create default roles for subscribed modules.
4. Grant Entity Super Admin all subscribed permissions.
5. Assign the first admin user.

### Phase 7: Browser Certification

Certify with Playwright:

- Entity Super Admin sees all subscribed modules.
- Non-subscribed modules do not appear.
- Role-specific menus match the access matrix.
- Manual URLs are blocked when permission or subscription is missing.
- GST and Payables report menus are complete.
- No duplicate menu branches remain.

## Phase 1 Completion Note

Completed locally on 2026-09-21:

- Canonical menu catalog now owns the final stage-aligned hierarchy for Purchase,
  Sales, Accounts, Catalog, Assets, Compliance, Reports, Admin, Payroll, and
  HRMS.
- Purchase and Sales documents sit under `Transactions`; setup pages sit under
  each module's `Setup` group.
- Inventory operations and inventory reports sit under `Reports > Inventory Hub`
  with `Setup`, `Operations`, `Analysis Reports`, and `Control Reports`.
- TDS, GST-TDS, and TCS compliance centers sit under
  `Reports > Financial Reports > Financial Hub`; GST return/reconciliation
  pages sit under `Reports > Compliance Reports`.
- Useful Payables report pages are canonicalized under `Reports > Payables
  Reports`; stale payroll/report shortcut shells and old top-level inventory /
  manufacturing roots are deactivated.
- Migration `0169_resync_stage_aligned_menu_cleanup` reapplies the final catalog
  to existing entities after migration.
- Local certification passed:
  - `python manage.py check`
  - `python manage.py test rbac.tests.test_access_catalog --keepdb`
  - `npx playwright test playwright/tests/rbac-canonical-menu.live.spec.ts --project=chromium`

## Signoff Gate

Implementation is not final until:

- Access matrix is reviewed.
- Menus match this hierarchy.
- Role templates match subscription packages.
- New entity onboarding creates the correct roles automatically.
- Browser certification passes for every default role.
