from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "final_2026_03"


MENU_CATALOG = [
    {"code": "dashboard", "name": "Dashboard", "menu_type": "group", "route_path": "", "route_name": "dashboard", "sort_order": 10, "parent_code": None, "icon": "layout-dashboard"},
    {"code": "dashboard.command-center", "name": "Command Center", "menu_type": "group", "route_path": "", "route_name": "dashboard-command-center", "sort_order": 1, "parent_code": "dashboard", "icon": "gauge"},
    {"code": "dashboard.command-center.home", "name": "Home", "menu_type": "screen", "route_path": "home", "route_name": "home", "sort_order": 1, "parent_code": "dashboard.command-center", "icon": "home"},
    {"code": "masters", "name": "Masters", "menu_type": "group", "route_path": "", "route_name": "masters", "sort_order": 20, "parent_code": None, "icon": "database"},
    {"code": "masters.accounts", "name": "Accounts Master", "menu_type": "group", "route_path": "", "route_name": "masters-accounts", "sort_order": 1, "parent_code": "masters", "icon": "book-open"},
    {"code": "masters.accounts.accounthead", "name": "Account Heads", "menu_type": "screen", "route_path": "accounthead", "route_name": "accounthead", "sort_order": 1, "parent_code": "masters.accounts", "icon": "folder-tree"},
    {"code": "masters.accounts.account", "name": "Accounts", "menu_type": "screen", "route_path": "account", "route_name": "account", "sort_order": 2, "parent_code": "masters.accounts", "icon": "users"},
    {"code": "masters.accounts.ledger", "name": "Ledger Master", "menu_type": "screen", "route_path": "ledger", "route_name": "ledger", "sort_order": 3, "parent_code": "masters.accounts", "icon": "book-text"},
    {"code": "masters.inventory", "name": "Inventory Master", "menu_type": "group", "route_path": "", "route_name": "masters-inventory", "sort_order": 2, "parent_code": "masters", "icon": "package"},
    {"code": "masters.inventory.product", "name": "Products", "menu_type": "screen", "route_path": "product", "route_name": "product", "sort_order": 1, "parent_code": "masters.inventory", "icon": "boxes"},
    {"code": "masters.inventory.productcategory", "name": "Product Categories", "menu_type": "screen", "route_path": "productcategory", "route_name": "productcategory", "sort_order": 2, "parent_code": "masters.inventory", "icon": "tags"},
    {"code": "masters.catalog", "name": "Catalog Workspace", "menu_type": "group", "route_path": "", "route_name": "masters-catalog", "sort_order": 3, "parent_code": "masters", "icon": "grid-2x2"},
    {"code": "masters.catalog.catalog-products", "name": "Catalog Workspace", "menu_type": "screen", "route_path": "catalog-products", "route_name": "catalog-products", "sort_order": 1, "parent_code": "masters.catalog", "icon": "layout-grid"},
    {"code": "masters.catalog.catalog-product-categories", "name": "Category Catalog", "menu_type": "screen", "route_path": "catalog-product-categories", "route_name": "catalog-product-categories", "sort_order": 2, "parent_code": "masters.catalog", "icon": "folder-kanban"},
    {"code": "masters.catalog.catalog-brands", "name": "Brands", "menu_type": "screen", "route_path": "catalog-brands", "route_name": "catalog-brands", "sort_order": 3, "parent_code": "masters.catalog", "icon": "badge-percent"},
    {"code": "masters.catalog.catalog-uoms", "name": "Units of Measure", "menu_type": "screen", "route_path": "catalog-uoms", "route_name": "catalog-uoms", "sort_order": 4, "parent_code": "masters.catalog", "icon": "ruler"},
    {"code": "masters.catalog.catalog-hsn-sac", "name": "HSN / SAC", "menu_type": "screen", "route_path": "catalog-hsn-sac", "route_name": "catalog-hsn-sac", "sort_order": 5, "parent_code": "masters.catalog", "icon": "hash"},
    {"code": "masters.catalog.catalog-price-lists", "name": "Price Lists", "menu_type": "screen", "route_path": "catalog-price-lists", "route_name": "catalog-price-lists", "sort_order": 6, "parent_code": "masters.catalog", "icon": "receipt-text"},
    {"code": "masters.catalog.catalog-product-attributes", "name": "Attributes", "menu_type": "screen", "route_path": "catalog-product-attributes", "route_name": "catalog-product-attributes", "sort_order": 7, "parent_code": "masters.catalog", "icon": "sliders-horizontal"},
    {"code": "sales", "name": "Sales", "menu_type": "group", "route_path": "", "route_name": "sales", "sort_order": 30, "parent_code": None, "icon": "trending-up"},
    {"code": "sales.transactions", "name": "Transactions", "menu_type": "group", "route_path": "", "route_name": "sales-transactions", "sort_order": 1, "parent_code": "sales", "icon": "receipt"},
    {"code": "sales.transactions.saleinvoice", "name": "Sales Invoice", "menu_type": "screen", "route_path": "saleinvoice", "route_name": "saleinvoice", "sort_order": 1, "parent_code": "sales.transactions", "icon": "file-text"},
    {"code": "purchase", "name": "Purchase", "menu_type": "group", "route_path": "", "route_name": "purchase", "sort_order": 40, "parent_code": None, "icon": "shopping-cart"},
    {"code": "purchase.transactions", "name": "Transactions", "menu_type": "group", "route_path": "", "route_name": "purchase-transactions", "sort_order": 1, "parent_code": "purchase", "icon": "clipboard-list"},
    {"code": "purchase.transactions.purchaseinvoice", "name": "Purchase Invoice", "menu_type": "screen", "route_path": "purchaseinvoice", "route_name": "purchaseinvoice", "sort_order": 1, "parent_code": "purchase.transactions", "icon": "file-stack"},
    {"code": "accounts", "name": "Accounts", "menu_type": "group", "route_path": "", "route_name": "accounts", "sort_order": 50, "parent_code": None, "icon": "calculator"},
    {"code": "accounts.vouchers", "name": "Vouchers", "menu_type": "group", "route_path": "", "route_name": "accounts-vouchers", "sort_order": 1, "parent_code": "accounts", "icon": "notebook"},
    {"code": "accounts.vouchers.journalvoucher", "name": "Journal Voucher", "menu_type": "screen", "route_path": "journalvoucher", "route_name": "journalvoucher", "sort_order": 1, "parent_code": "accounts.vouchers", "icon": "book"},
    {"code": "accounts.vouchers.bankvoucher", "name": "Bank Voucher", "menu_type": "screen", "route_path": "bankvoucher", "route_name": "bankvoucher", "sort_order": 2, "parent_code": "accounts.vouchers", "icon": "landmark"},
    {"code": "accounts.vouchers.cashvoucher", "name": "Cash Voucher", "menu_type": "screen", "route_path": "cashvoucher", "route_name": "cashvoucher", "sort_order": 3, "parent_code": "accounts.vouchers", "icon": "wallet"},
    {"code": "accounts.vouchers.receiptvoucher", "name": "Receipt Voucher", "menu_type": "screen", "route_path": "receiptvoucher", "route_name": "receiptvoucher", "sort_order": 4, "parent_code": "accounts.vouchers", "icon": "arrow-down-left"},
    {"code": "accounts.vouchers.paymentvoucher", "name": "Payment Voucher", "menu_type": "screen", "route_path": "paymentvoucher", "route_name": "paymentvoucher", "sort_order": 5, "parent_code": "accounts.vouchers", "icon": "arrow-up-right"},
    {"code": "compliance", "name": "Compliance", "menu_type": "group", "route_path": "", "route_name": "compliance", "sort_order": 60, "parent_code": None, "icon": "shield-check"},
    {"code": "compliance.tds", "name": "TDS", "menu_type": "group", "route_path": "", "route_name": "compliance-tds", "sort_order": 1, "parent_code": "compliance", "icon": "stamp"},
    {"code": "compliance.tds.tdsvoucher", "name": "TDS Voucher", "menu_type": "screen", "route_path": "tdsvoucher", "route_name": "tdsvoucher", "sort_order": 1, "parent_code": "compliance.tds", "icon": "file-badge"},
    {"code": "compliance.tcs-setup", "name": "TCS Setup", "menu_type": "group", "route_path": "", "route_name": "compliance-tcs-setup", "sort_order": 2, "parent_code": "compliance", "icon": "settings-2"},
    {"code": "compliance.tcs-setup.tcsconfig", "name": "TCS Config", "menu_type": "screen", "route_path": "tcsconfig", "route_name": "tcsconfig", "sort_order": 1, "parent_code": "compliance.tcs-setup", "icon": "sliders"},
    {"code": "compliance.tcs-setup.tcssections", "name": "TCS Sections", "menu_type": "screen", "route_path": "tcssections", "route_name": "tcssections", "sort_order": 2, "parent_code": "compliance.tcs-setup", "icon": "list-tree"},
    {"code": "compliance.tcs-setup.tcsrules", "name": "TCS Rules", "menu_type": "screen", "route_path": "tcsrules", "route_name": "tcsrules", "sort_order": 3, "parent_code": "compliance.tcs-setup", "icon": "scale"},
    {"code": "compliance.tcs-setup.tcspartyprofiles", "name": "Party Profiles", "menu_type": "screen", "route_path": "tcspartyprofiles", "route_name": "tcspartyprofiles", "sort_order": 4, "parent_code": "compliance.tcs-setup", "icon": "contact-round"},
    {"code": "compliance.tcs-operations", "name": "TCS Operations", "menu_type": "group", "route_path": "", "route_name": "compliance-tcs-operations", "sort_order": 3, "parent_code": "compliance", "icon": "briefcase-business"},
    {"code": "compliance.tcs-operations.tcsstatutory", "name": "Statutory Workspace", "menu_type": "screen", "route_path": "tcsstatutory", "route_name": "tcsstatutory", "sort_order": 1, "parent_code": "compliance.tcs-operations", "icon": "building-2"},
    {"code": "compliance.tcs-operations.tcsreturn27eq", "name": "Return 27EQ", "menu_type": "screen", "route_path": "tcsreturn27eq", "route_name": "tcsreturn27eq", "sort_order": 2, "parent_code": "compliance.tcs-operations", "icon": "file-check"},
    {"code": "reports", "name": "Reports", "menu_type": "group", "route_path": "", "route_name": "reports", "sort_order": 70, "parent_code": None, "icon": "bar-chart-3"},
    {"code": "reports.financial", "name": "Financial Reports", "menu_type": "group", "route_path": "", "route_name": "reports-financial", "sort_order": 1, "parent_code": "reports", "icon": "chart-column"},
    {"code": "reports.financial.trailbalance", "name": "Trial Balance", "menu_type": "screen", "route_path": "trailbalance", "route_name": "trailbalance", "sort_order": 1, "parent_code": "reports.financial", "icon": "scale-3d"},
    {"code": "reports.financial.ledgerbook", "name": "Ledger Book", "menu_type": "screen", "route_path": "ledgerbook", "route_name": "ledgerbook", "sort_order": 2, "parent_code": "reports.financial", "icon": "book-copy"},
    {"code": "reports.financial.balancesheet", "name": "Balance Sheet", "menu_type": "screen", "route_path": "balancesheet", "route_name": "balancesheet", "sort_order": 3, "parent_code": "reports.financial", "icon": "sheet"},
    {"code": "reports.financial.incomeexpenditurereport", "name": "P and L", "menu_type": "screen", "route_path": "incomeexpenditurereport", "route_name": "incomeexpenditurereport", "sort_order": 4, "parent_code": "reports.financial", "icon": "line-chart"},
    {"code": "reports.financial.tradingaccountstatement", "name": "Trading Account", "menu_type": "screen", "route_path": "tradingaccountstatement", "route_name": "tradingaccountstatement", "sort_order": 5, "parent_code": "reports.financial", "icon": "candlestick-chart"},
    {"code": "reports.financial.outstandingreport", "name": "Outstanding", "menu_type": "screen", "route_path": "outstandingreport", "route_name": "outstandingreport", "sort_order": 6, "parent_code": "reports.financial", "icon": "clock-3"},
    {"code": "reports.financial.accountsreceivableaging", "name": "AR Aging", "menu_type": "screen", "route_path": "accountsreceivableaging", "route_name": "accountsreceivableaging", "sort_order": 7, "parent_code": "reports.financial", "icon": "hourglass"},
    {"code": "reports.financial.accountspayableaging", "name": "AP Aging", "menu_type": "screen", "route_path": "accountspayableaging", "route_name": "accountspayableaging", "sort_order": 8, "parent_code": "reports.financial", "icon": "timer"},
    {"code": "reports.financial.interestcalculatorindividualreport", "name": "Interest Calculator", "menu_type": "screen", "route_path": "interestcalculatorindividualreport", "route_name": "interestcalculatorindividualreport", "sort_order": 9, "parent_code": "reports.financial", "icon": "percent"},
    {"code": "reports.compliance", "name": "Compliance Reports", "menu_type": "group", "route_path": "", "route_name": "reports-compliance", "sort_order": 2, "parent_code": "reports", "icon": "file-search"},
    {"code": "reports.compliance.tdsreport", "name": "TDS Report", "menu_type": "screen", "route_path": "tdsreport", "route_name": "tdsreport", "sort_order": 1, "parent_code": "reports.compliance", "icon": "scroll-text"},
    {"code": "reports.compliance.gstr3breport", "name": "GSTR-3B", "menu_type": "screen", "route_path": "gstr3breport", "route_name": "gstr3breport", "sort_order": 2, "parent_code": "reports.compliance", "icon": "file-spreadsheet"},
    {"code": "reports.compliance.tcsledgerreport", "name": "TCS Ledger", "menu_type": "screen", "route_path": "tcsledgerreport", "route_name": "tcsledgerreport", "sort_order": 3, "parent_code": "reports.compliance", "icon": "book-a"},
    {"code": "reports.compliance.tcsfilingpack", "name": "TCS Filing Pack", "menu_type": "screen", "route_path": "tcsfilingpack", "route_name": "tcsfilingpack", "sort_order": 4, "parent_code": "reports.compliance", "icon": "briefcase"},
    {"code": "reports.inventory", "name": "Stock Reports", "menu_type": "group", "route_path": "", "route_name": "reports-inventory", "sort_order": 3, "parent_code": "reports", "icon": "boxes"},
    {"code": "reports.inventory.stockdaybook", "name": "Stock Day Book", "menu_type": "screen", "route_path": "stockdaybook", "route_name": "stockdaybook", "sort_order": 1, "parent_code": "reports.inventory", "icon": "calendar-range"},
    {"code": "reports.inventory.stockbookreport", "name": "Stock Book", "menu_type": "screen", "route_path": "stockbookreport", "route_name": "stockbookreport", "sort_order": 2, "parent_code": "reports.inventory", "icon": "book-marked"},
    {"code": "reports.inventory.stockbooksummary", "name": "Stock Summary", "menu_type": "screen", "route_path": "stockbooksummary", "route_name": "stockbooksummary", "sort_order": 3, "parent_code": "reports.inventory", "icon": "summary"},
    {"code": "reports.inventory.stockmovementreport", "name": "Stock Movement", "menu_type": "screen", "route_path": "stockmovementreport", "route_name": "stockmovementreport", "sort_order": 4, "parent_code": "reports.inventory", "icon": "arrow-left-right"},
    {"code": "reports.inventory.stockagingreport", "name": "Stock Aging", "menu_type": "screen", "route_path": "stockagingreport", "route_name": "stockagingreport", "sort_order": 5, "parent_code": "reports.inventory", "icon": "archive"},
    {"code": "reports.assets", "name": "Asset Reports", "menu_type": "group", "route_path": "", "route_name": "reports-assets", "sort_order": 4, "parent_code": "reports", "icon": "building"},
    {"code": "reports.assets.fixed-asset-register", "name": "Fixed Asset Register", "menu_type": "screen", "route_path": "fixed-asset-register", "route_name": "fixed-asset-register", "sort_order": 1, "parent_code": "reports.assets", "icon": "clipboard-minus"},
    {"code": "reports.assets.depreciation-schedule", "name": "Depreciation Schedule", "menu_type": "screen", "route_path": "depreciation-schedule", "route_name": "depreciation-schedule", "sort_order": 2, "parent_code": "reports.assets", "icon": "calendar-clock"},
    {"code": "reports.assets.asset-events", "name": "Asset Events", "menu_type": "screen", "route_path": "asset-events", "route_name": "asset-events", "sort_order": 3, "parent_code": "reports.assets", "icon": "activity"},
    {"code": "reports.assets.asset-history", "name": "Asset History", "menu_type": "screen", "route_path": "asset-history", "route_name": "asset-history", "sort_order": 4, "parent_code": "reports.assets", "icon": "history"},
    {"code": "admin", "name": "Admin", "menu_type": "group", "route_path": "", "route_name": "admin", "sort_order": 80, "parent_code": None, "icon": "settings"},
    {"code": "admin.access", "name": "Access and Users", "menu_type": "group", "route_path": "", "route_name": "admin-access", "sort_order": 1, "parent_code": "admin", "icon": "shield"},
    {"code": "admin.access.user", "name": "Users", "menu_type": "screen", "route_path": "user", "route_name": "user", "sort_order": 1, "parent_code": "admin.access", "icon": "user-round"},
    {"code": "admin.access.role", "name": "Roles", "menu_type": "screen", "route_path": "role", "route_name": "role", "sort_order": 2, "parent_code": "admin.access", "icon": "badge-check"},
    {"code": "admin.access.rbacmanagement", "name": "Access Control", "menu_type": "screen", "route_path": "rbacmanagement", "route_name": "rbacmanagement", "sort_order": 3, "parent_code": "admin.access", "icon": "key-round"},
    {"code": "admin.access.changepassword", "name": "Change Password", "menu_type": "screen", "route_path": "changepassword", "route_name": "changepassword", "sort_order": 4, "parent_code": "admin.access", "icon": "lock-keyhole"},
    {"code": "admin.organization", "name": "Organization", "menu_type": "group", "route_path": "", "route_name": "admin-organization", "sort_order": 2, "parent_code": "admin", "icon": "building-2"},
    {"code": "admin.organization.branch", "name": "Branches", "menu_type": "screen", "route_path": "branch", "route_name": "branch", "sort_order": 1, "parent_code": "admin.organization", "icon": "git-branch"},
    {"code": "admin.organization.entityfinyear", "name": "Financial Years", "menu_type": "screen", "route_path": "entityfinyear", "route_name": "entityfinyear", "sort_order": 2, "parent_code": "admin.organization", "icon": "calendar-days"},
    {"code": "admin.configuration", "name": "Configuration", "menu_type": "group", "route_path": "", "route_name": "admin-configuration", "sort_order": 3, "parent_code": "admin", "icon": "sliders-vertical"},
    {"code": "admin.configuration.configuration", "name": "Configuration", "menu_type": "screen", "route_path": "configuration", "route_name": "configuration", "sort_order": 1, "parent_code": "admin.configuration", "icon": "settings-2"},
    {"code": "admin.configuration.setting", "name": "Document Settings", "menu_type": "screen", "route_path": "setting", "route_name": "setting", "sort_order": 2, "parent_code": "admin.configuration", "icon": "file-cog"},
    {"code": "admin.assets", "name": "Asset Administration", "menu_type": "group", "route_path": "", "route_name": "admin-assets", "sort_order": 4, "parent_code": "admin", "icon": "factory"},
    {"code": "admin.assets.asset-master", "name": "Asset Master", "menu_type": "screen", "route_path": "asset-master", "route_name": "asset-master", "sort_order": 1, "parent_code": "admin.assets", "icon": "building"},
    {"code": "admin.assets.asset-settings", "name": "Asset Settings", "menu_type": "screen", "route_path": "asset-settings", "route_name": "asset-settings", "sort_order": 2, "parent_code": "admin.assets", "icon": "wrench"},
    {"code": "admin.assets.depreciation-run", "name": "Depreciation Run", "menu_type": "screen", "route_path": "depreciation-run", "route_name": "depreciation-run", "sort_order": 3, "parent_code": "admin.assets", "icon": "play-circle"},
    {"code": "admin.payroll", "name": "Payroll", "menu_type": "group", "route_path": "", "route_name": "admin-payroll", "sort_order": 5, "parent_code": "admin", "icon": "wallet-cards"},
    {"code": "admin.payroll.salarycomponent", "name": "Salary Components", "menu_type": "screen", "route_path": "salarycomponent", "route_name": "salarycomponent", "sort_order": 1, "parent_code": "admin.payroll", "icon": "component"},
    {"code": "admin.payroll.employee", "name": "Employees", "menu_type": "screen", "route_path": "employee", "route_name": "employee", "sort_order": 2, "parent_code": "admin.payroll", "icon": "users-round"},
    {"code": "admin.payroll.employeesalary", "name": "Employee Salary", "menu_type": "screen", "route_path": "employeesalary", "route_name": "employeesalary", "sort_order": 3, "parent_code": "admin.payroll", "icon": "badge-indian-rupee"},
    {"code": "admin.payroll.payrollstructure", "name": "Payroll Structure", "menu_type": "screen", "route_path": "payrollstructure", "route_name": "payrollstructure", "sort_order": 4, "parent_code": "admin.payroll", "icon": "network"},
    {"code": "admin.payroll.compensation", "name": "Compensation", "menu_type": "screen", "route_path": "compensation", "route_name": "compensation", "sort_order": 5, "parent_code": "admin.payroll", "icon": "hand-coins"},
    {"code": "admin.payroll.emicalculator", "name": "EMI Calculator", "menu_type": "screen", "route_path": "emicalculator", "route_name": "emicalculator", "sort_order": 6, "parent_code": "admin.payroll", "icon": "calculator"},
]

MANAGED_ROOT_CODES = ("dashboard", "masters", "sales", "purchase", "accounts", "compliance", "reports", "admin", "assets", "catalog")


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
    for root_code in MANAGED_ROOT_CODES:
        if code == root_code or code.startswith(f"{root_code}."):
            return True
    return False


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
                "metadata": {"seed": "final_menu_catalog", "catalog_version": CATALOG_VERSION, "managed_root": _module_from_code(spec["code"])},
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
                "metadata": {"seed": "final_menu_catalog", "catalog_version": CATALOG_VERSION, "menu_code": spec["code"]},
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
    missing_role_permissions = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            missing_role_permissions.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "final_menu_catalog", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if missing_role_permissions:
        RolePermission.objects.bulk_create(missing_role_permissions)

    for menu in Menu.objects.filter(isactive=True).exclude(code__startswith="legacy."):
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
        ("rbac", "0012_add_asset_category_master_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
