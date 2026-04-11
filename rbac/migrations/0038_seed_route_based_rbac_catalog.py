from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "route_catalog_2026_04"


MENU_GROUPS = [
    ("dashboard", "Dashboard", 10, None, "layout-dashboard"),
    ("purchase", "Purchase", 20, None, "shopping-cart"),
    ("sales", "Sales", 30, None, "trending-up"),
    ("accounts", "Accounts", 40, None, "calculator"),
    ("catalog", "Catalog", 50, None, "boxes"),
    ("assets", "Assets", 60, None, "building"),
    ("compliance", "Compliance", 70, None, "shield-check"),
    ("reports", "Reports", 80, None, "bar-chart-3"),
    ("payroll", "Payroll", 90, None, "wallet-cards"),
    ("admin", "Admin", 100, None, "settings"),
]


ROUTE_SPECS = [
    {"route": "home", "group": "dashboard", "label": "Home", "feature": "", "access_mode": "setup", "view_permission": "dashboard.home.view", "actions": [], "sort_order": 1},
    {"route": "dashboard-analytics", "group": "dashboard", "label": "Analytics", "feature": "", "access_mode": "setup", "view_permission": "dashboard.analytics.view", "actions": [], "sort_order": 2},
    {"route": "dashboard", "group": "dashboard", "label": "Dashboard", "feature": "", "access_mode": "setup", "view_permission": "dashboard.view", "actions": [], "sort_order": 3},

    {"route": "purchaseinvoice", "group": "purchase", "label": "Purchase Invoice", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.invoice.view", "actions": ["purchase.invoice.create", "purchase.invoice.update", "purchase.invoice.delete", "purchase.invoice.print", "purchase.invoice.post", "purchase.invoice.unpost"], "sort_order": 1},
    {"route": "purchaseserviceinvoice", "group": "purchase", "label": "Purchase Service Invoice", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.invoice.view", "actions": ["purchase.invoice.create", "purchase.invoice.update", "purchase.invoice.delete", "purchase.invoice.print", "purchase.invoice.post", "purchase.invoice.unpost"], "sort_order": 2},
    {"route": "purchasecreditnoteinvoice", "group": "purchase", "label": "Purchase Credit Note", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.credit_note.view", "actions": ["purchase.credit_note.create", "purchase.credit_note.update", "purchase.credit_note.delete", "purchase.credit_note.print", "purchase.credit_note.post", "purchase.credit_note.unpost"], "sort_order": 3},
    {"route": "purchasedebitnoteinvoice", "group": "purchase", "label": "Purchase Debit Note", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.debit_note.view", "actions": ["purchase.debit_note.create", "purchase.debit_note.update", "purchase.debit_note.delete", "purchase.debit_note.print", "purchase.debit_note.post", "purchase.debit_note.unpost"], "sort_order": 4},
    {"route": "purchaseservicecreditnoteinvoice", "group": "purchase", "label": "Purchase Service Credit Note", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.credit_note.view", "actions": ["purchase.credit_note.create", "purchase.credit_note.update", "purchase.credit_note.delete", "purchase.credit_note.print", "purchase.credit_note.post", "purchase.credit_note.unpost"], "sort_order": 5},
    {"route": "purchaseservicedebitnoteinvoice", "group": "purchase", "label": "Purchase Service Debit Note", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.debit_note.view", "actions": ["purchase.debit_note.create", "purchase.debit_note.update", "purchase.debit_note.delete", "purchase.debit_note.print", "purchase.debit_note.post", "purchase.debit_note.unpost"], "sort_order": 6},
    {"route": "purchasesettings", "group": "purchase", "label": "Purchase Settings", "feature": "feature_purchase", "access_mode": "setup", "view_permission": "purchase.settings.view", "actions": ["purchase.settings.update"], "sort_order": 20},
    {"route": "purchasestatutory", "group": "purchase", "label": "Purchase Statutory", "feature": "feature_purchase", "access_mode": "operational", "view_permission": "purchase.statutory.view", "actions": [], "sort_order": 21},

    {"route": "saleinvoice", "group": "sales", "label": "Sales Invoice", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.invoice.view", "actions": ["sales.invoice.create", "sales.invoice.update", "sales.invoice.delete", "sales.invoice.print", "sales.invoice.post", "sales.invoice.unpost"], "sort_order": 1},
    {"route": "saleserviceinvoice", "group": "sales", "label": "Sales Service Invoice", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.invoice.view", "actions": ["sales.invoice.create", "sales.invoice.update", "sales.invoice.delete", "sales.invoice.print", "sales.invoice.post", "sales.invoice.unpost"], "sort_order": 2},
    {"route": "salecreditnoteinvoice", "group": "sales", "label": "Sales Credit Note", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.credit_note.view", "actions": ["sales.credit_note.create", "sales.credit_note.update", "sales.credit_note.delete", "sales.credit_note.print", "sales.credit_note.post", "sales.credit_note.unpost"], "sort_order": 3},
    {"route": "saledebitnoteinvoice", "group": "sales", "label": "Sales Debit Note", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.debit_note.view", "actions": ["sales.debit_note.create", "sales.debit_note.update", "sales.debit_note.delete", "sales.debit_note.print", "sales.debit_note.post", "sales.debit_note.unpost"], "sort_order": 4},
    {"route": "saleservicecreditnoteinvoice", "group": "sales", "label": "Sales Service Credit Note", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.credit_note.view", "actions": ["sales.credit_note.create", "sales.credit_note.update", "sales.credit_note.delete", "sales.credit_note.print", "sales.credit_note.post", "sales.credit_note.unpost"], "sort_order": 5},
    {"route": "saleservicedebitnoteinvoice", "group": "sales", "label": "Sales Service Debit Note", "feature": "feature_sales", "access_mode": "operational", "view_permission": "sales.debit_note.view", "actions": ["sales.debit_note.create", "sales.debit_note.update", "sales.debit_note.delete", "sales.debit_note.print", "sales.debit_note.post", "sales.debit_note.unpost"], "sort_order": 6},
    {"route": "salessettings", "group": "sales", "label": "Sales Settings", "feature": "feature_sales", "access_mode": "setup", "view_permission": "sales.settings.view", "actions": ["sales.settings.update"], "sort_order": 20},

    {"route": "paymentvoucher", "group": "accounts", "label": "Payment Voucher", "feature": "feature_financial", "access_mode": "operational", "view_permission": "voucher.payment.view", "actions": ["voucher.payment.create", "voucher.payment.update", "voucher.payment.delete", "voucher.payment.print", "voucher.payment.post", "voucher.payment.unpost"], "sort_order": 1},
    {"route": "receiptvoucher", "group": "accounts", "label": "Receipt Voucher", "feature": "feature_financial", "access_mode": "operational", "view_permission": "voucher.receipt.view", "actions": ["voucher.receipt.create", "voucher.receipt.update", "voucher.receipt.delete", "voucher.receipt.print", "voucher.receipt.post", "voucher.receipt.unpost"], "sort_order": 2},
    {"route": "cashvoucher", "group": "accounts", "label": "Cash Voucher", "feature": "feature_financial", "access_mode": "operational", "view_permission": "voucher.cash.view", "actions": ["voucher.cash.create", "voucher.cash.update", "voucher.cash.delete", "voucher.cash.print", "voucher.cash.post", "voucher.cash.unpost"], "sort_order": 3},
    {"route": "bankvoucher", "group": "accounts", "label": "Bank Voucher", "feature": "feature_financial", "access_mode": "operational", "view_permission": "voucher.bank.view", "actions": ["voucher.bank.create", "voucher.bank.update", "voucher.bank.delete", "voucher.bank.print", "voucher.bank.post", "voucher.bank.unpost"], "sort_order": 4},
    {"route": "journalvoucher", "group": "accounts", "label": "Journal Voucher", "feature": "feature_financial", "access_mode": "operational", "view_permission": "voucher.journal.view", "actions": ["voucher.journal.create", "voucher.journal.update", "voucher.journal.delete", "voucher.journal.print", "voucher.journal.post", "voucher.journal.unpost"], "sort_order": 5},
    {"route": "financialmaster/accounttypes", "group": "accounts", "label": "Account Types", "feature": "feature_financial", "access_mode": "operational", "view_permission": "financial.account_type.view", "actions": ["financial.account_type.create", "financial.account_type.update", "financial.account_type.delete"], "sort_order": 20},
    {"route": "financialmaster/accountheads", "group": "accounts", "label": "Account Heads", "feature": "feature_financial", "access_mode": "operational", "view_permission": "financial.account_head.view", "actions": ["financial.account_head.create", "financial.account_head.update", "financial.account_head.delete"], "sort_order": 21},
    {"route": "financialmaster/ledgers", "group": "accounts", "label": "Ledgers", "feature": "feature_financial", "access_mode": "operational", "view_permission": "financial.ledger.view", "actions": ["financial.ledger.create", "financial.ledger.update", "financial.ledger.delete"], "sort_order": 22},
    {"route": "financialmaster/accounts", "group": "accounts", "label": "Accounts", "feature": "feature_financial", "access_mode": "operational", "view_permission": "financial.account.view", "actions": ["financial.account.create", "financial.account.update", "financial.account.delete"], "sort_order": 23},
    {"route": "paymentsettings", "group": "accounts", "label": "Payment Settings", "feature": "feature_financial", "access_mode": "setup", "view_permission": "voucher.payment_settings.view", "actions": ["voucher.payment_settings.update"], "sort_order": 40},
    {"route": "receiptsettings", "group": "accounts", "label": "Receipt Settings", "feature": "feature_financial", "access_mode": "setup", "view_permission": "voucher.receipt_settings.view", "actions": ["voucher.receipt_settings.update"], "sort_order": 41},
    {"route": "vouchersettings", "group": "accounts", "label": "Voucher Settings", "feature": "feature_financial", "access_mode": "setup", "view_permission": "voucher.settings.view", "actions": ["voucher.settings.update"], "sort_order": 42},
    {"route": "staticaccountsettings", "group": "accounts", "label": "Static Account Settings", "feature": "feature_financial", "access_mode": "setup", "view_permission": "posting.static_account_settings.view", "actions": ["posting.static_account_settings.update"], "sort_order": 43},

    {"route": "catalogproducts", "group": "catalog", "label": "Products", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.product.view", "actions": ["catalog.product.create", "catalog.product.update", "catalog.product.delete"], "sort_order": 1},
    {"route": "catalogproductcategories", "group": "catalog", "label": "Product Categories", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.category.view", "actions": ["catalog.category.create", "catalog.category.update", "catalog.category.delete"], "sort_order": 2},
    {"route": "catalogbrands", "group": "catalog", "label": "Brands", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.brand.view", "actions": ["catalog.brand.create", "catalog.brand.update", "catalog.brand.delete"], "sort_order": 3},
    {"route": "cataloguoms", "group": "catalog", "label": "UOMs", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.uom.view", "actions": ["catalog.uom.create", "catalog.uom.update", "catalog.uom.delete"], "sort_order": 4},
    {"route": "cataloghsnsac", "group": "catalog", "label": "HSN SAC", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.hsn_sac.view", "actions": ["catalog.hsn_sac.create", "catalog.hsn_sac.update", "catalog.hsn_sac.delete"], "sort_order": 5},
    {"route": "catalogpricelists", "group": "catalog", "label": "Price Lists", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.price_list.view", "actions": ["catalog.price_list.create", "catalog.price_list.update", "catalog.price_list.delete"], "sort_order": 6},
    {"route": "catalogproductattributes", "group": "catalog", "label": "Product Attributes", "feature": "feature_inventory", "access_mode": "operational", "view_permission": "catalog.product_attribute.view", "actions": ["catalog.product_attribute.create", "catalog.product_attribute.update", "catalog.product_attribute.delete"], "sort_order": 7},

    {"route": "assetcategorymaster", "group": "assets", "label": "Asset Category Master", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.category.view", "actions": ["assets.category.create", "assets.category.update", "assets.category.delete"], "sort_order": 1},
    {"route": "assetmaster", "group": "assets", "label": "Asset Master", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.asset.view", "actions": ["assets.asset.create", "assets.asset.update", "assets.asset.delete"], "sort_order": 2},
    {"route": "depreciationrun", "group": "assets", "label": "Depreciation Run", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.depreciation_run.view", "actions": ["assets.depreciation_run.create"], "sort_order": 3},
    {"route": "assetsettings", "group": "assets", "label": "Asset Settings", "feature": "feature_assets", "access_mode": "setup", "view_permission": "assets.settings.view", "actions": ["assets.settings.update"], "sort_order": 20},

    {"route": "tcsreturn27eq", "group": "compliance", "label": "TCS Return 27EQ", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_return_27eq.view", "actions": ["compliance.tcs_return_27eq.export", "compliance.tcs_return_27eq.file"], "sort_order": 1},
    {"route": "tcsconfig", "group": "compliance", "label": "TCS Config", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_config.view", "actions": ["compliance.tcs_config.update"], "sort_order": 2},
    {"route": "tcssections", "group": "compliance", "label": "TCS Sections", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_section.view", "actions": ["compliance.tcs_section.create", "compliance.tcs_section.update", "compliance.tcs_section.delete"], "sort_order": 3},
    {"route": "tcsrules", "group": "compliance", "label": "TCS Rules", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_rule.view", "actions": ["compliance.tcs_rule.create", "compliance.tcs_rule.update", "compliance.tcs_rule.delete"], "sort_order": 4},
    {"route": "tcspartyprofiles", "group": "compliance", "label": "TCS Party Profiles", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_party_profile.view", "actions": ["compliance.tcs_party_profile.create", "compliance.tcs_party_profile.update", "compliance.tcs_party_profile.delete"], "sort_order": 5},
    {"route": "tcsstatutory", "group": "compliance", "label": "TCS Statutory", "feature": "feature_financial", "access_mode": "operational", "view_permission": "compliance.tcs_statutory.view", "actions": [], "sort_order": 6},

    {"route": "reports/payables", "group": "reports", "label": "Payables Reports", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.payables.view", "actions": ["reports.payables.export"], "sort_order": 1},
    {"route": "reports/purchaseregister", "group": "reports", "label": "Purchase Register", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.purchase_register.view", "actions": ["reports.purchase_register.export"], "sort_order": 2},
    {"route": "reports/salesregister", "group": "reports", "label": "Sales Register", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.sales_register.view", "actions": ["reports.sales_register.export"], "sort_order": 3},
    {"route": "trailbalance", "group": "reports", "label": "Trial Balance", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.trial_balance.view", "actions": ["reports.trial_balance.export"], "sort_order": 4},
    {"route": "daybook", "group": "reports", "label": "Daybook", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.daybook.view", "actions": ["reports.daybook.export"], "sort_order": 5},
    {"route": "salebook", "group": "reports", "label": "Sales Book", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.sales_book.view", "actions": ["reports.sales_book.export"], "sort_order": 6},
    {"route": "cashbook", "group": "reports", "label": "Cash Book", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.cash_book.view", "actions": ["reports.cash_book.export"], "sort_order": 7},
    {"route": "purchasebook", "group": "reports", "label": "Purchase Book", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.purchase_book.view", "actions": ["reports.purchase_book.export"], "sort_order": 8},
    {"route": "ledgerbook", "group": "reports", "label": "Ledger Book", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.ledger_book.view", "actions": ["reports.ledger_book.export"], "sort_order": 9},
    {"route": "gstreport", "group": "reports", "label": "GST Report", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.gst.view", "actions": ["reports.gst.export"], "sort_order": 10},
    {"route": "balancesheet", "group": "reports", "label": "Balance Sheet", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.balance_sheet.view", "actions": ["reports.balance_sheet.export"], "sort_order": 11},
    {"route": "incomeexpenditurereport", "group": "reports", "label": "Income Expenditure Report", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.income_expenditure.view", "actions": ["reports.income_expenditure.export"], "sort_order": 12},
    {"route": "tradingaccountstatement", "group": "reports", "label": "Trading Account Statement", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.trading_account.view", "actions": ["reports.trading_account.export"], "sort_order": 13},
    {"route": "tdsreport", "group": "reports", "label": "TDS Report", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.tds.view", "actions": ["reports.tds.export"], "sort_order": 14},
    {"route": "outstandingreport", "group": "reports", "label": "Outstanding Report", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.outstanding.view", "actions": ["reports.outstanding.export"], "sort_order": 15},
    {"route": "interestcalculatorindividualreport", "group": "reports", "label": "Interest Calculator", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.interest_calculator.view", "actions": ["reports.interest_calculator.export"], "sort_order": 16},
    {"route": "gstr3breport", "group": "reports", "label": "GSTR3B Report", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.gstr3b.view", "actions": ["reports.gstr3b.export"], "sort_order": 17},
    {"route": "accountsreceivableaging", "group": "reports", "label": "Accounts Receivable Aging", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.accounts_receivable_aging.view", "actions": ["reports.accounts_receivable_aging.export"], "sort_order": 18},
    {"route": "accountspayableaging", "group": "reports", "label": "Accounts Payable Aging", "feature": "feature_reporting", "access_mode": "operational", "view_permission": "reports.accounts_payable_aging.view", "actions": ["reports.accounts_payable_aging.export"], "sort_order": 19},
    {"route": "fixedassetregister", "group": "reports", "label": "Fixed Asset Register", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.fixed_asset_register.view", "actions": ["assets.fixed_asset_register.export"], "sort_order": 30},
    {"route": "depreciationschedule", "group": "reports", "label": "Depreciation Schedule", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.depreciation_schedule.view", "actions": ["assets.depreciation_schedule.export"], "sort_order": 31},
    {"route": "assetevents", "group": "reports", "label": "Asset Events", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.asset_events.view", "actions": ["assets.asset_events.export"], "sort_order": 32},
    {"route": "assethistory", "group": "reports", "label": "Asset History", "feature": "feature_assets", "access_mode": "operational", "view_permission": "assets.asset_history.view", "actions": ["assets.asset_history.export"], "sort_order": 33},

    {"route": "payroll", "group": "payroll", "label": "Payroll Dashboard", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.dashboard.view", "actions": [], "sort_order": 1},
    {"route": "salarycomponent", "group": "payroll", "label": "Salary Component", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.salary_component.view", "actions": ["payroll.salary_component.create", "payroll.salary_component.update", "payroll.salary_component.delete"], "sort_order": 2},
    {"route": "employee", "group": "payroll", "label": "Employee", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.employee.view", "actions": ["payroll.employee.create", "payroll.employee.update", "payroll.employee.delete"], "sort_order": 3},
    {"route": "employeesalary", "group": "payroll", "label": "Employee Salary", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.employee_salary.view", "actions": ["payroll.employee_salary.update"], "sort_order": 4},
    {"route": "payrollstructure", "group": "payroll", "label": "Payroll Structure", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.structure.view", "actions": ["payroll.structure.create", "payroll.structure.update", "payroll.structure.delete"], "sort_order": 5},
    {"route": "compensation", "group": "payroll", "label": "Compensation", "feature": "feature_payroll", "access_mode": "operational", "view_permission": "payroll.compensation.view", "actions": ["payroll.compensation.create", "payroll.compensation.update", "payroll.compensation.delete"], "sort_order": 6},

    {"route": "role", "group": "admin", "label": "Roles", "feature": "feature_rbac", "access_mode": "setup", "view_permission": "admin.role.view", "actions": ["admin.role.create", "admin.role.update", "admin.role.delete"], "sort_order": 1},
    {"route": "user", "group": "admin", "label": "Users", "feature": "feature_rbac", "access_mode": "setup", "view_permission": "admin.user.view", "actions": ["admin.user.create", "admin.user.update", "admin.user.delete"], "sort_order": 2},
    {"route": "rbacmanagement", "group": "admin", "label": "RBAC Management", "feature": "feature_rbac", "access_mode": "setup", "view_permission": "admin.rbac_management.view", "actions": ["admin.role.update", "admin.menu.view", "admin.menu.update", "admin.user_access.view", "admin.user_access.update"], "sort_order": 3},
    {"route": "invoicecustomfields", "group": "admin", "label": "Invoice Custom Fields", "feature": "feature_financial", "access_mode": "setup", "view_permission": "admin.invoice_custom_fields.view", "actions": ["admin.invoice_custom_fields.update"], "sort_order": 10},
    {"route": "changepassword", "group": "admin", "label": "Change Password", "feature": "", "access_mode": "setup", "view_permission": "admin.password.change", "actions": [], "sort_order": 11},
]


def _permission_parts(code):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _permission_name(code):
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "print": "Print",
        "post": "Post",
        "unpost": "Unpost",
        "export": "Export",
        "file": "File",
        "change": "Change",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1])
    resource = resource.title() if resource else parts[0].title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _menu_code(spec):
    return f"{spec['group']}.{spec['route'].replace('/', '.').replace(':', '_')}"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    managed_root_codes = {code for code, *_ in MENU_GROUPS}
    menu_by_code = {}
    target_menu_codes = set()
    target_permission_codes = set()
    permission_ids = set()

    for code, name, sort_order, parent_code, icon in MENU_GROUPS:
        parent = menu_by_code.get(parent_code)
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={
                "parent_id": parent.id if parent else None,
                "name": name,
                "menu_type": "group",
                "route_path": "",
                "route_name": code,
                "icon": icon,
                "sort_order": sort_order,
                "is_system_menu": True,
                "metadata": {"seed": "route_catalog", "catalog_version": CATALOG_VERSION, "group": code},
                "isactive": True,
            },
        )
        menu_by_code[code] = menu
        target_menu_codes.add(code)

    for spec in ROUTE_SPECS:
        parent = menu_by_code[spec["group"]]
        menu_code = _menu_code(spec)
        menu, _ = Menu.objects.update_or_create(
            code=menu_code,
            defaults={
                "parent_id": parent.id,
                "name": spec["label"],
                "menu_type": "screen",
                "route_path": spec["route"],
                "route_name": spec["route"].replace("/", "-").replace(":", ""),
                "icon": "",
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "route_catalog",
                    "catalog_version": CATALOG_VERSION,
                    "feature": spec["feature"],
                    "access_mode": spec["access_mode"],
                    "route": spec["route"],
                    "menu_group": spec["group"],
                },
                "isactive": True,
            },
        )
        target_menu_codes.add(menu_code)

        all_codes = [spec["view_permission"], *spec["actions"]]
        for permission_code in all_codes:
            module, resource, action = _permission_parts(permission_code)
            permission, _ = Permission.objects.update_or_create(
                code=permission_code,
                defaults={
                    "name": _permission_name(permission_code),
                    "module": module,
                    "resource": resource,
                    "action": action,
                    "description": _permission_name(permission_code),
                    "scope_type": PERMISSION_SCOPE_ENTITY,
                    "is_system_defined": True,
                    "metadata": {
                        "seed": "route_catalog",
                        "catalog_version": CATALOG_VERSION,
                        "feature": spec["feature"],
                        "access_mode": spec["access_mode"],
                        "route": spec["route"],
                        "menu_code": menu_code,
                    },
                    "isactive": True,
                },
            )
            target_permission_codes.add(permission_code)
            permission_ids.add(permission.id)
            relation_type = MENU_RELATION_VISIBILITY if permission_code == spec["view_permission"] else MENU_RELATION_ACTION
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission.id,
                relation_type=relation_type,
                defaults={"isactive": True},
            )

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=list(permission_ids)).values_list("role_id", "permission_id"))
    inserts = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "route_catalog", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)

    for menu in Menu.objects.filter(isactive=True):
        if menu.code in managed_root_codes or any(menu.code.startswith(f"{root}.") for root in managed_root_codes):
            if menu.code not in target_menu_codes:
                menu.isactive = False
                menu.save(update_fields=["isactive", "updated_at"])

    managed_modules = {spec["view_permission"].split(".")[0] for spec in ROUTE_SPECS}
    for permission in Permission.objects.filter(isactive=True, is_system_defined=True, module__in=managed_modules):
        if permission.code not in target_permission_codes:
            permission.isactive = False
            permission.save(update_fields=["isactive", "updated_at"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_codes = {code for code, *_ in MENU_GROUPS}
    menu_codes.update(_menu_code(spec) for spec in ROUTE_SPECS)
    permission_codes = set()
    for spec in ROUTE_SPECS:
        permission_codes.add(spec["view_permission"])
        permission_codes.update(spec["actions"])

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0037_add_service_invoice_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
