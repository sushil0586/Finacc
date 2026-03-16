from django.db import migrations

MENU_RELATION_VISIBILITY = "visibility"
PERMISSION_SCOPE_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
CATALOG_VERSION = "hierarchy_repair_2026_03_14"

GROUP_SPECS = [
    ("dashboard.command-center", "dashboard", "Command Center", "dashboard-command-center", 1, "gauge"),
    ("masters.accounts", "masters", "Accounts Master", "masters-accounts", 1, "book-open"),
    ("masters.inventory", "masters", "Inventory Master", "masters-inventory", 2, "package"),
    ("masters.catalog", "masters", "Catalog Workspace", "masters-catalog", 3, "grid-2x2"),
    ("sales.transactions", "sales", "Transactions", "sales-transactions", 1, "receipt"),
    ("purchase.transactions", "purchase", "Transactions", "purchase-transactions", 1, "clipboard-list"),
    ("purchase.compliance", "purchase", "Compliance", "purchase-compliance", 2, "shield-check"),
    ("inventory.operations", "inventory", "Operations", "inventory-operations", 1, "boxes"),
    ("accounts.vouchers", "accounts", "Vouchers", "accounts-vouchers", 1, "notebook"),
    ("accounts.notes", "accounts", "Notes", "accounts-notes", 2, "file-text"),
    ("compliance.tds", "compliance", "TDS", "compliance-tds", 1, "stamp"),
    ("compliance.tcs-setup", "compliance", "TCS Setup", "compliance-tcs-setup", 2, "settings-2"),
    ("compliance.tcs-operations", "compliance", "TCS Operations", "compliance-tcs-operations", 3, "briefcase-business"),
    ("reports.financial", "reports", "Financial Reports", "reports-financial", 1, "chart-column"),
    ("reports.compliance", "reports", "Compliance Reports", "reports-compliance", 2, "file-search"),
    ("reports.inventory", "reports", "Stock Reports", "reports-inventory", 3, "boxes"),
    ("reports.assets", "reports", "Asset Reports", "reports-assets", 4, "building"),
    ("admin.access", "admin", "Access and Users", "admin-access", 1, "shield"),
    ("admin.organization", "admin", "Organization", "admin-organization", 2, "building-2"),
    ("admin.configuration", "admin", "Configuration", "admin-configuration", 3, "sliders-vertical"),
    ("admin.assets", "admin", "Asset Administration", "admin-assets", 4, "factory"),
    ("admin.payroll", "admin", "Payroll", "admin-payroll", 5, "wallet-cards"),
]

SCREEN_SPECS = [
    ("dashboard.home", "dashboard.command-center", "Command Center", "home", "home", 1, "home"),
    ("masters.accounthead", "masters.accounts", "Account Heads", "accounthead", "accounthead", 1, "folder-tree"),
    ("masters.account", "masters.accounts", "Accounts", "account", "account", 2, "users"),
    ("masters.ledger", "masters.accounts", "Ledger Master", "ledger", "ledger", 3, "book-text"),
    ("masters.product", "masters.inventory", "Products", "product", "product", 1, "boxes"),
    ("masters.productcategory", "masters.inventory", "Product Categories", "productcategory", "productcategory", 2, "tags"),
    ("masters.catalog-products", "masters.catalog", "Catalog Workspace", "catalog-products", "catalog-products", 1, "layout-grid"),
    ("masters.catalog-product-categories", "masters.catalog", "Category Catalog", "catalog-product-categories", "catalog-product-categories", 2, "folder-kanban"),
    ("masters.catalog-brands", "masters.catalog", "Brands", "catalog-brands", "catalog-brands", 3, "badge-percent"),
    ("masters.catalog-uoms", "masters.catalog", "Units of Measure", "catalog-uoms", "catalog-uoms", 4, "ruler"),
    ("masters.catalog-hsn-sac", "masters.catalog", "HSN / SAC", "catalog-hsn-sac", "catalog-hsn-sac", 5, "hash"),
    ("masters.catalog-price-lists", "masters.catalog", "Price Lists", "catalog-price-lists", "catalog-price-lists", 6, "receipt-text"),
    ("masters.catalog-product-attributes", "masters.catalog", "Attributes", "catalog-product-attributes", "catalog-product-attributes", 7, "sliders-horizontal"),
    ("sales.saleinvoice", "sales.transactions", "Sales Invoice", "saleinvoice", "saleinvoice", 1, "file-text"),
    ("purchase.purchaseinvoice", "purchase.transactions", "Purchase Invoice", "purchaseinvoice", "purchaseinvoice", 1, "file-stack"),
    ("purchase.purchasecreditnoteinvoice", "purchase.transactions", "Purchase Credit Note", "purchasecreditnoteinvoice", "purchasecreditnoteinvoice", 2, "receipt-text"),
    ("purchase.purchasestatutory", "purchase.compliance", "Purchase Compliance", "purchasestatutory", "purchasestatutory", 1, "shield-check"),
    ("inventory.stockmanagement", "inventory.operations", "Stock Management", "stockmanagement", "stockmanagement", 1, "package-open"),
    ("inventory.stockvoucher", "inventory.operations", "Stock Voucher", "stockvoucher", "stockvoucher", 2, "clipboard-list"),
    ("inventory.productionorder", "inventory.operations", "Production Order", "productionorder", "productionorder", 3, "factory"),
    ("inventory.productionvoucher", "inventory.operations", "Production Voucher", "productionvoucher", "productionvoucher", 4, "file-cog"),
    ("inventory.bulkinsertproduct", "inventory.operations", "Bulk Product Import", "bulkinsertproduct", "bulkinsertproduct", 5, "files"),
    ("accounts.journalvoucher", "accounts.vouchers", "Journal Voucher", "journalvoucher", "journalvoucher", 1, "book"),
    ("accounts.bankvoucher", "accounts.vouchers", "Bank Voucher", "bankvoucher", "bankvoucher", 2, "landmark"),
    ("accounts.cashvoucher", "accounts.vouchers", "Cash Voucher", "cashvoucher", "cashvoucher", 3, "wallet"),
    ("accounts.receiptvoucher", "accounts.vouchers", "Receipt Voucher", "receiptvoucher", "receiptvoucher", 4, "arrow-down-left"),
    ("accounts.paymentvoucher", "accounts.vouchers", "Payment Voucher", "paymentvoucher", "paymentvoucher", 5, "arrow-up-right"),
    ("accounts.creditnote", "accounts.notes", "Credit Note", "creditnote", "creditnote", 1, "file-minus"),
    ("accounts.debitnote", "accounts.notes", "Debit Note", "debitnote", "debitnote", 2, "file-plus"),
    ("compliance.tdsvoucher", "compliance.tds", "TDS Voucher", "tdsvoucher", "tdsvoucher", 1, "file-badge"),
    ("compliance.tcsconfig", "compliance.tcs-setup", "TCS Config", "tcsconfig", "tcsconfig", 1, "sliders"),
    ("compliance.tcssections", "compliance.tcs-setup", "TCS Sections", "tcssections", "tcssections", 2, "list-tree"),
    ("compliance.tcsrules", "compliance.tcs-setup", "TCS Rules", "tcsrules", "tcsrules", 3, "scale"),
    ("compliance.tcspartyprofiles", "compliance.tcs-setup", "Party Profiles", "tcspartyprofiles", "tcspartyprofiles", 4, "contact-round"),
    ("compliance.tcsstatutory", "compliance.tcs-operations", "Statutory Workspace", "tcsstatutory", "tcsstatutory", 1, "building-2"),
    ("compliance.tcsreturn27eq", "compliance.tcs-operations", "Return 27EQ", "tcsreturn27eq", "tcsreturn27eq", 2, "file-check"),
    ("reports.trailbalance", "reports.financial", "Trial Balance", "trailbalance", "trailbalance", 1, "scale-3d"),
    ("reports.daybook", "reports.financial", "Day Book", "daybook", "daybook", 2, "calendar-range"),
    ("reports.salebook", "reports.financial", "Sales Book", "salebook", "salebook", 3, "book-open-check"),
    ("reports.purchasebook", "reports.financial", "Purchase Book", "purchasebook", "purchasebook", 4, "book-copy"),
    ("reports.cashbook", "reports.financial", "Cash Book", "cashbook", "cashbook", 5, "wallet-cards"),
    ("reports.cashbooksummary", "reports.financial", "Cash Summary", "cashbooksummary", "cashbooksummary", 6, "scroll"),
    ("reports.ledgerbook", "reports.financial", "Ledger Book", "ledgerbook", "ledgerbook", 7, "book-text"),
    ("reports.ledgersummary", "reports.financial", "Ledger Summary", "ledgersummary", "ledgersummary", 8, "book-a"),
    ("reports.balancesheet", "reports.financial", "Balance Sheet", "balancesheet", "balancesheet", 9, "sheet"),
    ("reports.incomeexpenditurereport", "reports.financial", "P and L", "incomeexpenditurereport", "incomeexpenditurereport", 10, "line-chart"),
    ("reports.tradingaccountstatement", "reports.financial", "Trading Account", "tradingaccountstatement", "tradingaccountstatement", 11, "candlestick-chart"),
    ("reports.outstandingreport", "reports.financial", "Outstanding", "outstandingreport", "outstandingreport", 12, "clock-3"),
    ("reports.vendoroutstanding", "reports.financial", "Vendor Outstanding", "vendoroutstanding", "vendoroutstanding", 13, "wallet-minimal"),
    ("reports.accountsreceivableaging", "reports.financial", "AR Aging", "accountsreceivableaging", "accountsreceivableaging", 14, "hourglass"),
    ("reports.accountspayableaging", "reports.financial", "AP Aging", "accountspayableaging", "accountspayableaging", 15, "timer"),
("reports.vendorledgerstatement", "reports.financial", "Vendor Ledger Statement", "vendorledgerstatement", "vendorledgerstatement", 18, "book-text"),
    ("reports.payablesclosepack", "reports.financial", "Payables Close Pack", "payablesclosepack", "payablesclosepack", 19, "briefcase-business"),
    ("reports.vendorsettlementhistory", "reports.financial", "Vendor Settlement History", "vendorsettlementhistory", "vendorsettlementhistory", 20, "hand-coins"),
    ("reports.vendornoteregister", "reports.financial", "Vendor Debit/Credit Note Register", "vendornoteregister", "vendornoteregister", 21, "receipt-text"),
    ("reports.apglreconciliation", "reports.financial", "AP to GL Reconciliation", "apglreconciliation", "apglreconciliation", 16, "scale"),
    ("reports.vendorbalanceexceptions", "reports.financial", "Vendor Balance Exceptions", "vendorbalanceexceptions", "vendorbalanceexceptions", 17, "alert-triangle"),
    ("reports.interestcalculatorindividualreport", "reports.financial", "Interest Calculator", "interestcalculatorindividualreport", "interestcalculatorindividualreport", 15, "percent"),
    ("reports.gstreport", "reports.compliance", "GST Report", "gstreport", "gstreport", 1, "file-spreadsheet"),
    ("reports.tdsreport", "reports.compliance", "TDS Report", "tdsreport", "tdsreport", 2, "scroll-text"),
    ("reports.gstr3breport", "reports.compliance", "GSTR-3B", "gstr3breport", "gstr3breport", 3, "file-spreadsheet"),
    ("reports.tcsledgerreport", "reports.compliance", "TCS Ledger", "tcsledgerreport", "tcsledgerreport", 4, "book-a"),
    ("reports.tcsfilingpack", "reports.compliance", "TCS Filing Pack", "tcsfilingpack", "tcsfilingpack", 5, "briefcase"),
    ("reports.stockledgersummary", "reports.inventory", "Stock Ledger Summary", "stockledgersummary", "stockledgersummary", 1, "boxes"),
    ("reports.stockledgerbook", "reports.inventory", "Stock Ledger Book", "stockledgerbook", "stockledgerbook", 2, "book-marked"),
    ("reports.stockdaybook", "reports.inventory", "Stock Day Book", "stockdaybook", "stockdaybook", 3, "calendar-days"),
    ("reports.stockbookreport", "reports.inventory", "Stock Book", "stockbookreport", "stockbookreport", 4, "book-copy"),
    ("reports.stockbooksummary", "reports.inventory", "Stock Summary", "stockbooksummary", "stockbooksummary", 5, "summary"),
    ("reports.stockmovementreport", "reports.inventory", "Stock Movement", "stockmovementreport", "stockmovementreport", 6, "arrow-left-right"),
    ("reports.stockagingreport", "reports.inventory", "Stock Aging", "stockagingreport", "stockagingreport", 7, "archive"),
    ("reports.fixed-asset-register", "reports.assets", "Fixed Asset Register", "fixed-asset-register", "fixed-asset-register", 1, "clipboard-minus"),
    ("reports.depreciation-schedule", "reports.assets", "Depreciation Schedule", "depreciation-schedule", "depreciation-schedule", 2, "calendar-clock"),
    ("reports.asset-events", "reports.assets", "Asset Events", "asset-events", "asset-events", 3, "activity"),
    ("reports.asset-history", "reports.assets", "Asset History", "asset-history", "asset-history", 4, "history"),
    ("admin.user", "admin.access", "Users", "user", "user", 1, "user-round"),
    ("admin.role", "admin.access", "Roles", "role", "role", 2, "badge-check"),
    ("admin.rbacmanagement", "admin.access", "Access Control", "rbacmanagement", "rbacmanagement", 3, "key-round"),
    ("admin.changepassword", "admin.access", "Change Password", "changepassword", "changepassword", 4, "lock-keyhole"),
    ("admin.branch", "admin.organization", "Branches", "branch", "branch", 1, "git-branch"),
    ("admin.entityfinyear", "admin.organization", "Financial Years", "entityfinyear", "entityfinyear", 2, "calendar-days"),
    ("admin.configuration.configuration", "admin.configuration", "Configuration", "configuration", "configuration", 1, "settings-2"),
    ("admin.setting", "admin.configuration", "Document Settings", "setting", "setting", 2, "file-cog"),
    ("admin.asset-master", "admin.assets", "Asset Master", "asset-master", "asset-master", 1, "building"),
    ("admin.asset-settings", "admin.assets", "Asset Settings", "asset-settings", "asset-settings", 2, "wrench"),
    ("admin.depreciation-run", "admin.assets", "Depreciation Run", "depreciation-run", "depreciation-run", 3, "play-circle"),
    ("admin.salarycomponent", "admin.payroll", "Salary Components", "salarycomponent", "salarycomponent", 1, "component"),
    ("admin.employee", "admin.payroll", "Employees", "employee", "employee", 2, "users-round"),
    ("admin.employeesalary", "admin.payroll", "Employee Salary", "employeesalary", "employeesalary", 3, "badge-indian-rupee"),
    ("admin.payrollstructure", "admin.payroll", "Payroll Structure", "payrollstructure", "payrollstructure", 4, "network"),
    ("admin.compensation", "admin.payroll", "Compensation", "compensation", "compensation", 5, "hand-coins"),
    ("admin.emicalculator", "admin.payroll", "EMI Calculator", "emicalculator", "emicalculator", 6, "calculator"),
]

ROOT_SPECS = [
    ("dashboard", "Dashboard", 10, "layout-dashboard"),
    ("masters", "Masters", 20, "database"),
    ("sales", "Sales", 30, "trending-up"),
    ("purchase", "Purchase", 40, "shopping-cart"),
    ("inventory", "Inventory", 50, "boxes"),
    ("accounts", "Accounts", 60, "calculator"),
    ("compliance", "Compliance", 70, "shield-check"),
    ("reports", "Reports", 80, "bar-chart-3"),
    ("admin", "Admin", 90, "settings"),
]


def _module_from_code(code):
    return code.split(".", 1)[0]


def _resource_from_code(code):
    return code.split(".")[-1].replace("-", "_")


def _permission_tuple(code, name, menu_type):
    module = _module_from_code(code)
    resource = _resource_from_code(code)
    action = "view" if menu_type == "screen" else "access"
    name_prefix = "View" if menu_type == "screen" else "Access"
    return (f"{module}.{resource}.{action}", f"{name_prefix} {name}", module, resource, action)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_by_code = {}
    permission_ids = []

    for code, name, sort_order, icon in ROOT_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={"parent_id": None, "name": name, "menu_type": "group", "route_path": "", "route_name": code, "icon": icon, "sort_order": sort_order, "is_system_menu": True, "metadata": {"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION, "managed_root": code}, "isactive": True},
        )
        menu_by_code[code] = menu

    for code, parent_code, name, route_name, sort_order, icon in GROUP_SPECS:
        parent = menu_by_code[parent_code]
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={"parent_id": parent.id, "name": name, "menu_type": "group", "route_path": "", "route_name": route_name, "icon": icon, "sort_order": sort_order, "is_system_menu": True, "metadata": {"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION, "managed_root": _module_from_code(code)}, "isactive": True},
        )
        menu_by_code[code] = menu
        pcode, pname, module, resource, action = _permission_tuple(code, name, "group")
        perm, _ = Permission.objects.update_or_create(
            code=pcode,
            defaults={"name": pname, "module": module, "resource": resource, "action": action, "description": pname, "scope_type": PERMISSION_SCOPE_ENTITY, "is_system_defined": True, "metadata": {"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION, "menu_code": code}, "isactive": True},
        )
        permission_ids.append(perm.id)
        MenuPermission.objects.update_or_create(menu_id=menu.id, permission_id=perm.id, relation_type=MENU_RELATION_VISIBILITY, defaults={"isactive": True})

    for code, parent_code, name, route_path, route_name, sort_order, icon in SCREEN_SPECS:
        parent = menu_by_code[parent_code]
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={"parent_id": parent.id, "name": name, "menu_type": "screen", "route_path": route_path, "route_name": route_name, "icon": icon, "sort_order": sort_order, "is_system_menu": True, "metadata": {"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION, "managed_root": _module_from_code(code)}, "isactive": True},
        )
        pcode, pname, module, resource, action = _permission_tuple(code, name, "screen")
        perm, _ = Permission.objects.update_or_create(
            code=pcode,
            defaults={"name": pname, "module": module, "resource": resource, "action": action, "description": pname, "scope_type": PERMISSION_SCOPE_ENTITY, "is_system_defined": True, "metadata": {"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION, "menu_code": code}, "isactive": True},
        )
        permission_ids.append(perm.id)
        MenuPermission.objects.update_or_create(menu_id=menu.id, permission_id=perm.id, relation_type=MENU_RELATION_VISIBILITY, defaults={"isactive": True})

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    existing = set(RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id"))
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) not in existing:
                rows.append(RolePermission(role_id=role_id, permission_id=permission_id, effect=ROLE_PERMISSION_ALLOW, metadata={"seed": "hierarchy_repair", "catalog_version": CATALOG_VERSION}, isactive=True))
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("rbac", "0020_sync_current_menu_catalog")]
    operations = [migrations.RunPython(forwards, backwards)]
