from django.db import migrations


SEED_TAG = "operational_menu_section_normalization"
CATALOG_VERSION = "operational_sections_2026_07_15"


GROUP_SPECS = (
    {
        "code": "accounts.vouchers",
        "parent_code": "accounts",
        "name": "Vouchers",
        "route_name": "accounts-vouchers",
        "icon": "notebook",
        "sort_order": 1,
    },
    {
        "code": "accounts.financial_masters",
        "parent_code": "accounts",
        "name": "Financial Masters",
        "route_name": "accounts-financial-masters",
        "icon": "book",
        "sort_order": 2,
    },
    {
        "code": "accounts.settings",
        "parent_code": "accounts",
        "name": "Settings",
        "route_name": "accounts-settings",
        "icon": "gear",
        "sort_order": 3,
    },
    {
        "code": "sales.transactions",
        "parent_code": "sales",
        "name": "Transactions",
        "route_name": "sales-transactions",
        "icon": "receipt",
        "sort_order": 1,
    },
    {
        "code": "sales.channels",
        "parent_code": "sales",
        "name": "Channels and Tools",
        "route_name": "sales-channels",
        "icon": "shop",
        "sort_order": 2,
    },
    {
        "code": "sales.setup",
        "parent_code": "sales",
        "name": "Setup",
        "route_name": "sales-setup",
        "icon": "sliders",
        "sort_order": 3,
    },
    {
        "code": "purchase.transactions",
        "parent_code": "purchase",
        "name": "Transactions",
        "route_name": "purchase-transactions",
        "icon": "file-earmark-text",
        "sort_order": 1,
    },
    {
        "code": "purchase.tools",
        "parent_code": "purchase",
        "name": "Tools",
        "route_name": "purchase-tools",
        "icon": "tools",
        "sort_order": 2,
    },
    {
        "code": "purchase.compliance",
        "parent_code": "purchase",
        "name": "Compliance",
        "route_name": "purchase-compliance",
        "icon": "shield-check",
        "sort_order": 3,
    },
    {
        "code": "purchase.setup",
        "parent_code": "purchase",
        "name": "Setup",
        "route_name": "purchase-setup",
        "icon": "gear",
        "sort_order": 4,
    },
    {
        "code": "catalog.products",
        "parent_code": "catalog",
        "name": "Products",
        "route_name": "catalog-products",
        "icon": "boxes",
        "sort_order": 1,
    },
    {
        "code": "catalog.classification",
        "parent_code": "catalog",
        "name": "Classification",
        "route_name": "catalog-classification",
        "icon": "tags",
        "sort_order": 2,
    },
    {
        "code": "catalog.commercial",
        "parent_code": "catalog",
        "name": "Commercial",
        "route_name": "catalog-commercial",
        "icon": "cash-stack",
        "sort_order": 3,
    },
    {
        "code": "compliance.gst_and_tds",
        "parent_code": "compliance",
        "name": "GST and TDS",
        "route_name": "compliance-gst-tds",
        "icon": "file-earmark-bar-graph",
        "sort_order": 1,
    },
    {
        "code": "compliance.tcs_setup",
        "parent_code": "compliance",
        "name": "TCS Setup",
        "route_name": "compliance-tcs-setup",
        "icon": "sliders",
        "sort_order": 2,
    },
    {
        "code": "compliance.tcs_operations",
        "parent_code": "compliance",
        "name": "TCS Operations",
        "route_name": "compliance-tcs-operations",
        "icon": "briefcase",
        "sort_order": 3,
    },
    {
        "code": "admin.access",
        "parent_code": "admin",
        "name": "Access and Users",
        "route_name": "admin-access",
        "icon": "shield-lock",
        "sort_order": 1,
    },
    {
        "code": "admin.configuration",
        "parent_code": "admin",
        "name": "Configuration",
        "route_name": "admin-configuration",
        "icon": "sliders",
        "sort_order": 2,
    },
    {
        "code": "admin.module_controls",
        "parent_code": "admin",
        "name": "Module Controls",
        "route_name": "admin-module-controls",
        "icon": "toggles2",
        "sort_order": 3,
    },
)


MENU_REPARENT_SPECS = (
    ("accounts.paymentvoucher", "accounts.vouchers", 1),
    ("accounts.receiptvoucher", "accounts.vouchers", 2),
    ("accounts.cashvoucher", "accounts.vouchers", 3),
    ("accounts.bankvoucher", "accounts.vouchers", 4),
    ("accounts.journalvoucher", "accounts.vouchers", 5),
    ("accounts.financialmaster.accounttypes", "accounts.financial_masters", 1),
    ("accounts.financialmaster.accountheads", "accounts.financial_masters", 2),
    ("accounts.financialmaster.ledgers", "accounts.financial_masters", 3),
    ("accounts.financialmaster.accounts", "accounts.financial_masters", 4),
    ("accounts.paymentsettings", "accounts.settings", 1),
    ("accounts.receiptsettings", "accounts.settings", 2),
    ("accounts.vouchersettings", "accounts.settings", 3),
    ("accounts.staticaccountsettings", "accounts.settings", 4),

    ("sales.saleinvoice", "sales.transactions", 1),
    ("sales.saleserviceinvoice", "sales.transactions", 2),
    ("sales.salecreditnoteinvoice", "sales.transactions", 3),
    ("sales.saledebitnoteinvoice", "sales.transactions", 4),
    ("sales.saleservicecreditnoteinvoice", "sales.transactions", 5),
    ("sales.saleservicedebitnoteinvoice", "sales.transactions", 6),
    ("sales.retail_sale_entry", "sales.channels", 1),
    ("sales.commerce_line_tester", "sales.channels", 2),
    ("sales.sales-bulk-print-center", "sales.channels", 3),
    ("sales.sales-legacy-import", "sales.channels", 4),
    ("sales.salessettings", "sales.setup", 1),

    ("purchase.purchaseinvoice", "purchase.transactions", 1),
    ("purchase.purchaseserviceinvoice", "purchase.transactions", 2),
    ("purchase.purchasecreditnoteinvoice", "purchase.transactions", 3),
    ("purchase.purchasedebitnoteinvoice", "purchase.transactions", 4),
    ("purchase.purchaseservicecreditnoteinvoice", "purchase.transactions", 5),
    ("purchase.purchaseservicedebitnoteinvoice", "purchase.transactions", 6),
    ("purchase.purchase-legacy-import", "purchase.tools", 1),
    ("purchase.purchasestatutory", "purchase.compliance", 1),
    ("purchase.purchasesettings", "purchase.setup", 1),

    ("catalog.catalogproducts", "catalog.products", 1),
    ("catalog.catalogproductcategories", "catalog.products", 2),
    ("catalog.catalogbrands", "catalog.classification", 1),
    ("catalog.cataloguoms", "catalog.classification", 2),
    ("catalog.cataloghsnsac", "catalog.classification", 3),
    ("catalog.catalogpricelists", "catalog.commercial", 1),
    ("catalog.catalogproductattributes", "catalog.commercial", 2),

    ("compliance.gst_reconciliation", "compliance.gst_and_tds", 1),
    ("compliance.gstdsconfig", "compliance.gst_and_tds", 2),
    ("compliance.tcsreturn27eq", "compliance.tcs_operations", 1),
    ("compliance.tcsstatutory", "compliance.tcs_operations", 2),
    ("compliance.tcsconfig", "compliance.tcs_setup", 1),
    ("compliance.tcssections", "compliance.tcs_setup", 2),
    ("compliance.tcsrules", "compliance.tcs_setup", 3),
    ("compliance.tcspartyprofiles", "compliance.tcs_setup", 4),

    ("admin.role", "admin.access", 1),
    ("admin.user", "admin.access", 2),
    ("admin.rbacmanagement", "admin.access", 3),
    ("admin.changepassword", "admin.access", 4),
    ("admin.invoicecustomfields", "admin.configuration", 1),
    ("admin.manufacturing_settings", "admin.module_controls", 1),
    ("admin.commerce_promotions", "admin.module_controls", 2),
)


def _ensure_group(Menu, spec):
    parent = Menu.objects.filter(code=spec["parent_code"], isactive=True).first()
    if parent is None:
        return None

    menu, _ = Menu.objects.update_or_create(
        code=spec["code"],
        defaults={
            "parent_id": parent.id,
            "name": spec["name"],
            "menu_type": "group",
            "route_path": "",
            "route_name": spec["route_name"],
            "icon": spec["icon"],
            "sort_order": spec["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": spec["code"],
                "section": True,
            },
            "isactive": True,
        },
    )
    return menu


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")

    groups_by_code = {}
    for spec in GROUP_SPECS:
        group = _ensure_group(Menu, spec)
        if group is not None:
            groups_by_code[spec["code"]] = group

    for menu_code, parent_code, sort_order in MENU_REPARENT_SPECS:
        menu = Menu.objects.filter(code=menu_code, isactive=True).first()
        parent = groups_by_code.get(parent_code)
        if menu is None or parent is None:
            continue

        metadata = dict(menu.metadata or {})
        metadata["seed"] = SEED_TAG
        metadata["catalog_version"] = CATALOG_VERSION
        metadata["section_parent"] = parent_code
        menu.parent_id = parent.id
        menu.sort_order = sort_order
        menu.metadata = metadata
        menu.save(update_fields=["parent_id", "sort_order", "metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0134_realign_inventory_hub_menu_hierarchy"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
