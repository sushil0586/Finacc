from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "current_2026_03_14"


MENU_CATALOG = [
    {"code": "dashboard", "name": "Dashboard", "menu_type": "group", "route_path": "", "route_name": "dashboard", "sort_order": 10, "parent_code": None, "icon": "layout-dashboard"},
    {"code": "dashboard.home", "name": "Command Center", "menu_type": "screen", "route_path": "home", "route_name": "home", "sort_order": 1, "parent_code": "dashboard", "icon": "home"},

    {"code": "masters", "name": "Masters", "menu_type": "group", "route_path": "", "route_name": "masters", "sort_order": 20, "parent_code": None, "icon": "database"},
    {"code": "masters.accounthead", "name": "Account Heads", "menu_type": "screen", "route_path": "accounthead", "route_name": "accounthead", "sort_order": 1, "parent_code": "masters", "icon": "folder-tree"},
    {"code": "masters.account", "name": "Accounts", "menu_type": "screen", "route_path": "account", "route_name": "account", "sort_order": 2, "parent_code": "masters", "icon": "users"},
    {"code": "masters.ledger", "name": "Ledger Master", "menu_type": "screen", "route_path": "ledger", "route_name": "ledger", "sort_order": 3, "parent_code": "masters", "icon": "book-text"},
    {"code": "masters.product", "name": "Products", "menu_type": "screen", "route_path": "product", "route_name": "product", "sort_order": 4, "parent_code": "masters", "icon": "boxes"},
    {"code": "masters.productcategory", "name": "Product Categories", "menu_type": "screen", "route_path": "productcategory", "route_name": "productcategory", "sort_order": 5, "parent_code": "masters", "icon": "tags"},
    {"code": "masters.catalog-products", "name": "Catalog Workspace", "menu_type": "screen", "route_path": "catalog-products", "route_name": "catalog-products", "sort_order": 6, "parent_code": "masters", "icon": "layout-grid"},
    {"code": "masters.catalog-product-categories", "name": "Category Catalog", "menu_type": "screen", "route_path": "catalog-product-categories", "route_name": "catalog-product-categories", "sort_order": 7, "parent_code": "masters", "icon": "folder-kanban"},
    {"code": "masters.catalog-brands", "name": "Brands", "menu_type": "screen", "route_path": "catalog-brands", "route_name": "catalog-brands", "sort_order": 8, "parent_code": "masters", "icon": "badge-percent"},
    {"code": "masters.catalog-uoms", "name": "Units of Measure", "menu_type": "screen", "route_path": "catalog-uoms", "route_name": "catalog-uoms", "sort_order": 9, "parent_code": "masters", "icon": "ruler"},
    {"code": "masters.catalog-hsn-sac", "name": "HSN / SAC", "menu_type": "screen", "route_path": "catalog-hsn-sac", "route_name": "catalog-hsn-sac", "sort_order": 10, "parent_code": "masters", "icon": "hash"},
    {"code": "masters.catalog-price-lists", "name": "Price Lists", "menu_type": "screen", "route_path": "catalog-price-lists", "route_name": "catalog-price-lists", "sort_order": 11, "parent_code": "masters", "icon": "receipt-text"},
    {"code": "masters.catalog-product-attributes", "name": "Attributes", "menu_type": "screen", "route_path": "catalog-product-attributes", "route_name": "catalog-product-attributes", "sort_order": 12, "parent_code": "masters", "icon": "sliders-horizontal"},

    {"code": "sales", "name": "Sales", "menu_type": "group", "route_path": "", "route_name": "sales", "sort_order": 30, "parent_code": None, "icon": "trending-up"},
    {"code": "sales.saleinvoice", "name": "Sales Invoice", "menu_type": "screen", "route_path": "saleinvoice", "route_name": "saleinvoice", "sort_order": 1, "parent_code": "sales", "icon": "file-text"},
    {"code": "sales.sales-settings", "name": "Sales Settings", "menu_type": "screen", "route_path": "sales-settings", "route_name": "sales-settings", "sort_order": 2, "parent_code": "sales", "icon": "sliders-horizontal"},

    {"code": "purchase", "name": "Purchase", "menu_type": "group", "route_path": "", "route_name": "purchase", "sort_order": 40, "parent_code": None, "icon": "shopping-cart"},
    {"code": "purchase.purchaseinvoice", "name": "Purchase Invoice", "menu_type": "screen", "route_path": "purchaseinvoice", "route_name": "purchaseinvoice", "sort_order": 1, "parent_code": "purchase", "icon": "file-stack"},
    {"code": "purchase.purchasecreditnoteinvoice", "name": "Purchase Credit Note", "menu_type": "screen", "route_path": "purchasecreditnoteinvoice", "route_name": "purchasecreditnoteinvoice", "sort_order": 2, "parent_code": "purchase", "icon": "receipt-text"},
    {"code": "purchase.purchasestatutory", "name": "Purchase Compliance", "menu_type": "screen", "route_path": "purchasestatutory", "route_name": "purchasestatutory", "sort_order": 3, "parent_code": "purchase", "icon": "shield-check"},

    {"code": "inventory", "name": "Inventory", "menu_type": "group", "route_path": "", "route_name": "inventory", "sort_order": 50, "parent_code": None, "icon": "boxes"},
    {"code": "inventory.stockmanagement", "name": "Stock Management", "menu_type": "screen", "route_path": "stockmanagement", "route_name": "stockmanagement", "sort_order": 1, "parent_code": "inventory", "icon": "package-open"},
    {"code": "inventory.stockvoucher", "name": "Stock Voucher", "menu_type": "screen", "route_path": "stockvoucher", "route_name": "stockvoucher", "sort_order": 2, "parent_code": "inventory", "icon": "clipboard-list"},
    {"code": "inventory.productionorder", "name": "Production Order", "menu_type": "screen", "route_path": "productionorder", "route_name": "productionorder", "sort_order": 3, "parent_code": "inventory", "icon": "factory"},
    {"code": "inventory.productionvoucher", "name": "Production Voucher", "menu_type": "screen", "route_path": "productionvoucher", "route_name": "productionvoucher", "sort_order": 4, "parent_code": "inventory", "icon": "file-cog"},
    {"code": "inventory.bulkinsertproduct", "name": "Bulk Product Import", "menu_type": "screen", "route_path": "bulkinsertproduct", "route_name": "bulkinsertproduct", "sort_order": 5, "parent_code": "inventory", "icon": "files"},

    {"code": "accounts", "name": "Accounts", "menu_type": "group", "route_path": "", "route_name": "accounts", "sort_order": 60, "parent_code": None, "icon": "calculator"},
    {"code": "accounts.journalvoucher", "name": "Journal Voucher", "menu_type": "screen", "route_path": "journalvoucher", "route_name": "journalvoucher", "sort_order": 1, "parent_code": "accounts", "icon": "book"},
    {"code": "accounts.bankvoucher", "name": "Bank Voucher", "menu_type": "screen", "route_path": "bankvoucher", "route_name": "bankvoucher", "sort_order": 2, "parent_code": "accounts", "icon": "landmark"},
    {"code": "accounts.cashvoucher", "name": "Cash Voucher", "menu_type": "screen", "route_path": "cashvoucher", "route_name": "cashvoucher", "sort_order": 3, "parent_code": "accounts", "icon": "wallet"},
    {"code": "accounts.receiptvoucher", "name": "Receipt Voucher", "menu_type": "screen", "route_path": "receiptvoucher", "route_name": "receiptvoucher", "sort_order": 4, "parent_code": "accounts", "icon": "arrow-down-left"},
    {"code": "accounts.paymentvoucher", "name": "Payment Voucher", "menu_type": "screen", "route_path": "paymentvoucher", "route_name": "paymentvoucher", "sort_order": 5, "parent_code": "accounts", "icon": "arrow-up-right"},
    {"code": "accounts.creditnote", "name": "Credit Note", "menu_type": "screen", "route_path": "creditnote", "route_name": "creditnote", "sort_order": 6, "parent_code": "accounts", "icon": "file-minus"},
    {"code": "accounts.debitnote", "name": "Debit Note", "menu_type": "screen", "route_path": "debitnote", "route_name": "debitnote", "sort_order": 7, "parent_code": "accounts", "icon": "file-plus"},

    {"code": "compliance", "name": "Compliance", "menu_type": "group", "route_path": "", "route_name": "compliance", "sort_order": 70, "parent_code": None, "icon": "shield-check"},
    {"code": "compliance.tdsvoucher", "name": "TDS Voucher", "menu_type": "screen", "route_path": "tdsvoucher", "route_name": "tdsvoucher", "sort_order": 1, "parent_code": "compliance", "icon": "file-badge"},
    {"code": "compliance.tcsconfig", "name": "TCS Config", "menu_type": "screen", "route_path": "tcsconfig", "route_name": "tcsconfig", "sort_order": 2, "parent_code": "compliance", "icon": "sliders"},
    {"code": "compliance.tcssections", "name": "TCS Sections", "menu_type": "screen", "route_path": "tcssections", "route_name": "tcssections", "sort_order": 3, "parent_code": "compliance", "icon": "list-tree"},
    {"code": "compliance.tcsrules", "name": "TCS Rules", "menu_type": "screen", "route_path": "tcsrules", "route_name": "tcsrules", "sort_order": 4, "parent_code": "compliance", "icon": "scale"},
    {"code": "compliance.tcspartyprofiles", "name": "Party Profiles", "menu_type": "screen", "route_path": "tcspartyprofiles", "route_name": "tcspartyprofiles", "sort_order": 5, "parent_code": "compliance", "icon": "contact-round"},
    {"code": "compliance.tcsstatutory", "name": "Statutory Workspace", "menu_type": "screen", "route_path": "tcsstatutory", "route_name": "tcsstatutory", "sort_order": 6, "parent_code": "compliance", "icon": "building-2"},
    {"code": "compliance.tcsreturn27eq", "name": "Return 27EQ", "menu_type": "screen", "route_path": "tcsreturn27eq", "route_name": "tcsreturn27eq", "sort_order": 7, "parent_code": "compliance", "icon": "file-check"},

    {"code": "reports", "name": "Reports", "menu_type": "group", "route_path": "", "route_name": "reports", "sort_order": 80, "parent_code": None, "icon": "bar-chart-3"},
    {"code": "reports.trailbalance", "name": "Trial Balance", "menu_type": "screen", "route_path": "trailbalance", "route_name": "trailbalance", "sort_order": 1, "parent_code": "reports", "icon": "scale-3d"},
    {"code": "reports.daybook", "name": "Day Book", "menu_type": "screen", "route_path": "daybook", "route_name": "daybook", "sort_order": 2, "parent_code": "reports", "icon": "calendar-range"},
    {"code": "reports.salebook", "name": "Sales Book", "menu_type": "screen", "route_path": "salebook", "route_name": "salebook", "sort_order": 3, "parent_code": "reports", "icon": "book-open-check"},
    {"code": "reports.purchasebook", "name": "Purchase Book", "menu_type": "screen", "route_path": "purchasebook", "route_name": "purchasebook", "sort_order": 4, "parent_code": "reports", "icon": "book-copy"},
    {"code": "reports.cashbook", "name": "Cash Book", "menu_type": "screen", "route_path": "cashbook", "route_name": "cashbook", "sort_order": 5, "parent_code": "reports", "icon": "wallet-cards"},
    {"code": "reports.cashbooksummary", "name": "Cash Summary", "menu_type": "screen", "route_path": "cashbooksummary", "route_name": "cashbooksummary", "sort_order": 6, "parent_code": "reports", "icon": "scroll"},
    {"code": "reports.ledgerbook", "name": "Ledger Book", "menu_type": "screen", "route_path": "ledgerbook", "route_name": "ledgerbook", "sort_order": 7, "parent_code": "reports", "icon": "book-text"},
    {"code": "reports.ledgersummary", "name": "Ledger Summary", "menu_type": "screen", "route_path": "ledgersummary", "route_name": "ledgersummary", "sort_order": 8, "parent_code": "reports", "icon": "book-a"},
    {"code": "reports.stockledgersummary", "name": "Stock Ledger Summary", "menu_type": "screen", "route_path": "stockledgersummary", "route_name": "stockledgersummary", "sort_order": 9, "parent_code": "reports", "icon": "boxes"},
    {"code": "reports.stockledgerbook", "name": "Stock Ledger Book", "menu_type": "screen", "route_path": "stockledgerbook", "route_name": "stockledgerbook", "sort_order": 10, "parent_code": "reports", "icon": "book-marked"},
    {"code": "reports.gstreport", "name": "GST Report", "menu_type": "screen", "route_path": "gstreport", "route_name": "gstreport", "sort_order": 11, "parent_code": "reports", "icon": "file-spreadsheet"},
    {"code": "reports.tdsreport", "name": "TDS Report", "menu_type": "screen", "route_path": "tdsreport", "route_name": "tdsreport", "sort_order": 12, "parent_code": "reports", "icon": "scroll-text"},
    {"code": "reports.balancesheet", "name": "Balance Sheet", "menu_type": "screen", "route_path": "balancesheet", "route_name": "balancesheet", "sort_order": 13, "parent_code": "reports", "icon": "sheet"},
    {"code": "reports.incomeexpenditurereport", "name": "P and L", "menu_type": "screen", "route_path": "incomeexpenditurereport", "route_name": "incomeexpenditurereport", "sort_order": 14, "parent_code": "reports", "icon": "line-chart"},
    {"code": "reports.tradingaccountstatement", "name": "Trading Account", "menu_type": "screen", "route_path": "tradingaccountstatement", "route_name": "tradingaccountstatement", "sort_order": 15, "parent_code": "reports", "icon": "candlestick-chart"},
    {"code": "reports.outstandingreport", "name": "Outstanding", "menu_type": "screen", "route_path": "outstandingreport", "route_name": "outstandingreport", "sort_order": 16, "parent_code": "reports", "icon": "clock-3"},
    {"code": "reports.vendoroutstanding", "name": "Vendor Outstanding", "menu_type": "screen", "route_path": "vendoroutstanding", "route_name": "vendoroutstanding", "sort_order": 17, "parent_code": "reports", "icon": "wallet-minimal"},
    {"code": "reports.accountsreceivableaging", "name": "AR Aging", "menu_type": "screen", "route_path": "accountsreceivableaging", "route_name": "accountsreceivableaging", "sort_order": 18, "parent_code": "reports", "icon": "hourglass"},
    {"code": "reports.accountspayableaging", "name": "AP Aging", "menu_type": "screen", "route_path": "accountspayableaging", "route_name": "accountspayableaging", "sort_order": 19, "parent_code": "reports", "icon": "timer"},
{"code": "reports.vendorledgerstatement", "name": "Vendor Ledger Statement", "menu_type": "screen", "route_path": "vendorledgerstatement", "route_name": "vendorledgerstatement", "sort_order": 22, "parent_code": "reports", "icon": "book-text"},
    {"code": "reports.payablesclosepack", "name": "Payables Close Pack", "menu_type": "screen", "route_path": "payablesclosepack", "route_name": "payablesclosepack", "sort_order": 23, "parent_code": "reports", "icon": "briefcase-business"},
    {"code": "reports.vendorsettlementhistory", "name": "Vendor Settlement History", "menu_type": "screen", "route_path": "vendorsettlementhistory", "route_name": "vendorsettlementhistory", "sort_order": 24, "parent_code": "reports", "icon": "hand-coins"},
    {"code": "reports.vendornoteregister", "name": "Vendor Debit/Credit Note Register", "menu_type": "screen", "route_path": "vendornoteregister", "route_name": "vendornoteregister", "sort_order": 25, "parent_code": "reports", "icon": "receipt-text"},
    {"code": "reports.apglreconciliation", "name": "AP to GL Reconciliation", "menu_type": "screen", "route_path": "apglreconciliation", "route_name": "apglreconciliation", "sort_order": 20, "parent_code": "reports", "icon": "scale"},
    {"code": "reports.vendorbalanceexceptions", "name": "Vendor Balance Exceptions", "menu_type": "screen", "route_path": "vendorbalanceexceptions", "route_name": "vendorbalanceexceptions", "sort_order": 21, "parent_code": "reports", "icon": "alert-triangle"},
    {"code": "reports.gstr3breport", "name": "GSTR-3B", "menu_type": "screen", "route_path": "gstr3breport", "route_name": "gstr3breport", "sort_order": 19, "parent_code": "reports", "icon": "file-spreadsheet"},
    {"code": "reports.stockdaybook", "name": "Stock Day Book", "menu_type": "screen", "route_path": "stockdaybook", "route_name": "stockdaybook", "sort_order": 20, "parent_code": "reports", "icon": "calendar-days"},
    {"code": "reports.stockbookreport", "name": "Stock Book", "menu_type": "screen", "route_path": "stockbookreport", "route_name": "stockbookreport", "sort_order": 21, "parent_code": "reports", "icon": "book-copy"},
    {"code": "reports.stockbooksummary", "name": "Stock Summary", "menu_type": "screen", "route_path": "stockbooksummary", "route_name": "stockbooksummary", "sort_order": 22, "parent_code": "reports", "icon": "summary"},
    {"code": "reports.stockmovementreport", "name": "Stock Movement", "menu_type": "screen", "route_path": "stockmovementreport", "route_name": "stockmovementreport", "sort_order": 23, "parent_code": "reports", "icon": "arrow-left-right"},
    {"code": "reports.stockagingreport", "name": "Stock Aging", "menu_type": "screen", "route_path": "stockagingreport", "route_name": "stockagingreport", "sort_order": 24, "parent_code": "reports", "icon": "archive"},
    {"code": "reports.interestcalculatorindividualreport", "name": "Interest Calculator", "menu_type": "screen", "route_path": "interestcalculatorindividualreport", "route_name": "interestcalculatorindividualreport", "sort_order": 25, "parent_code": "reports", "icon": "percent"},
    {"code": "reports.tcsledgerreport", "name": "TCS Ledger", "menu_type": "screen", "route_path": "tcsledgerreport", "route_name": "tcsledgerreport", "sort_order": 26, "parent_code": "reports", "icon": "book-a"},
    {"code": "reports.tcsfilingpack", "name": "TCS Filing Pack", "menu_type": "screen", "route_path": "tcsfilingpack", "route_name": "tcsfilingpack", "sort_order": 27, "parent_code": "reports", "icon": "briefcase"},
    {"code": "reports.fixed-asset-register", "name": "Fixed Asset Register", "menu_type": "screen", "route_path": "fixed-asset-register", "route_name": "fixed-asset-register", "sort_order": 28, "parent_code": "reports", "icon": "clipboard-minus"},
    {"code": "reports.depreciation-schedule", "name": "Depreciation Schedule", "menu_type": "screen", "route_path": "depreciation-schedule", "route_name": "depreciation-schedule", "sort_order": 29, "parent_code": "reports", "icon": "calendar-clock"},
    {"code": "reports.asset-events", "name": "Asset Events", "menu_type": "screen", "route_path": "asset-events", "route_name": "asset-events", "sort_order": 30, "parent_code": "reports", "icon": "activity"},
    {"code": "reports.asset-history", "name": "Asset History", "menu_type": "screen", "route_path": "asset-history", "route_name": "asset-history", "sort_order": 31, "parent_code": "reports", "icon": "history"},

    {"code": "admin", "name": "Admin", "menu_type": "group", "route_path": "", "route_name": "admin", "sort_order": 90, "parent_code": None, "icon": "settings"},
    {"code": "admin.user", "name": "Users", "menu_type": "screen", "route_path": "user", "route_name": "user", "sort_order": 1, "parent_code": "admin", "icon": "user-round"},
    {"code": "admin.role", "name": "Roles", "menu_type": "screen", "route_path": "role", "route_name": "role", "sort_order": 2, "parent_code": "admin", "icon": "badge-check"},
    {"code": "admin.branch", "name": "Branches", "menu_type": "screen", "route_path": "branch", "route_name": "branch", "sort_order": 3, "parent_code": "admin", "icon": "git-branch"},
    {"code": "admin.entityfinyear", "name": "Financial Years", "menu_type": "screen", "route_path": "entityfinyear", "route_name": "entityfinyear", "sort_order": 4, "parent_code": "admin", "icon": "calendar-days"},
    {"code": "admin.configuration", "name": "Configuration", "menu_type": "screen", "route_path": "configuration", "route_name": "configuration", "sort_order": 5, "parent_code": "admin", "icon": "settings-2"},
    {"code": "admin.setting", "name": "Document Settings", "menu_type": "screen", "route_path": "setting", "route_name": "setting", "sort_order": 6, "parent_code": "admin", "icon": "file-cog"},
    {"code": "admin.rbacmanagement", "name": "Access Control", "menu_type": "screen", "route_path": "rbacmanagement", "route_name": "rbacmanagement", "sort_order": 7, "parent_code": "admin", "icon": "key-round"},
    {"code": "admin.asset-master", "name": "Asset Master", "menu_type": "screen", "route_path": "asset-master", "route_name": "asset-master", "sort_order": 8, "parent_code": "admin", "icon": "building"},
    {"code": "admin.asset-settings", "name": "Asset Settings", "menu_type": "screen", "route_path": "asset-settings", "route_name": "asset-settings", "sort_order": 9, "parent_code": "admin", "icon": "wrench"},
    {"code": "admin.depreciation-run", "name": "Depreciation Run", "menu_type": "screen", "route_path": "depreciation-run", "route_name": "depreciation-run", "sort_order": 10, "parent_code": "admin", "icon": "play-circle"},
    {"code": "admin.salarycomponent", "name": "Salary Components", "menu_type": "screen", "route_path": "salarycomponent", "route_name": "salarycomponent", "sort_order": 11, "parent_code": "admin", "icon": "component"},
    {"code": "admin.employee", "name": "Employees", "menu_type": "screen", "route_path": "employee", "route_name": "employee", "sort_order": 12, "parent_code": "admin", "icon": "users-round"},
    {"code": "admin.employeesalary", "name": "Employee Salary", "menu_type": "screen", "route_path": "employeesalary", "route_name": "employeesalary", "sort_order": 13, "parent_code": "admin", "icon": "badge-indian-rupee"},
    {"code": "admin.payrollstructure", "name": "Payroll Structure", "menu_type": "screen", "route_path": "payrollstructure", "route_name": "payrollstructure", "sort_order": 14, "parent_code": "admin", "icon": "network"},
    {"code": "admin.compensation", "name": "Compensation", "menu_type": "screen", "route_path": "compensation", "route_name": "compensation", "sort_order": 15, "parent_code": "admin", "icon": "hand-coins"},
    {"code": "admin.emicalculator", "name": "EMI Calculator", "menu_type": "screen", "route_path": "emicalculator", "route_name": "emicalculator", "sort_order": 16, "parent_code": "admin", "icon": "calculator"},
    {"code": "admin.changepassword", "name": "Change Password", "menu_type": "screen", "route_path": "changepassword", "route_name": "changepassword", "sort_order": 17, "parent_code": "admin", "icon": "lock-keyhole"},
]

MANAGED_ROOT_CODES = ("dashboard", "masters", "sales", "purchase", "inventory", "accounts", "compliance", "reports", "admin", "assets", "catalog")


def _module_from_code(code):
    return code.split(".", 1)[0]


def _resource_from_code(code):
    return code.split(".")[-1].replace("-", "_")


def _permission_tuple(spec):
    module = _module_from_code(spec["code"])
    resource = _resource_from_code(spec["code"])
    action = "view" if spec["menu_type"] == "screen" else "access"
    name_prefix = "View" if spec["menu_type"] == "screen" else "Access"
    return (f"{module}.{resource}.{action}", f"{name_prefix} {spec['name']}", module, resource, action)


def _managed_code(code):
    return any(code == root or code.startswith(f"{root}.") for root in MANAGED_ROOT_CODES)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_by_code = {}
    permission_ids = []
    target_codes = {spec["code"] for spec in MENU_CATALOG}

    for spec in MENU_CATALOG:
        parent = menu_by_code.get(spec["parent_code"])
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent.id if parent else None,
                "name": spec["name"],
                "menu_type": spec["menu_type"],
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {"seed": "current_menu_catalog", "catalog_version": CATALOG_VERSION, "managed_root": _module_from_code(spec["code"])},
                "isactive": True,
            },
        )
        menu_by_code[spec["code"]] = menu

        permission_code, permission_name, module, resource, action = _permission_tuple(spec)
        permission, _ = Permission.objects.update_or_create(
            code=permission_code,
            defaults={
                "name": permission_name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": permission_name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": "current_menu_catalog", "catalog_version": CATALOG_VERSION, "menu_code": spec["code"]},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id"))
    missing = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) not in existing_pairs:
                missing.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": "current_menu_catalog", "catalog_version": CATALOG_VERSION},
                        isactive=True,
                    )
                )
    if missing:
        RolePermission.objects.bulk_create(missing)

    for menu in Menu.objects.filter(isactive=True):
        if _managed_code(menu.code) and menu.code not in target_codes:
            menu.isactive = False
            menu.save(update_fields=["isactive", "updated_at"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    target_codes = [spec["code"] for spec in MENU_CATALOG]
    permission_codes = [_permission_tuple(spec)[0] for spec in MENU_CATALOG]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=target_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0019_move_sales_settings_direct_under_sales"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
