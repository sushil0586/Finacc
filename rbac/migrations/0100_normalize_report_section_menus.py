from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "report_section_normalization_2026_05_08"


SECTION_GROUP_SPECS = (
    {
        "code": "reports.controls",
        "name": "Controls Reports",
        "parent_code": "reports",
        "route_name": "reports-controls",
        "icon": "sliders-horizontal",
        "sort_order": 1,
    },
    {
        "code": "reports.receivables",
        "name": "Receivables Reports",
        "parent_code": "reports",
        "route_name": "reports-receivables",
        "icon": "folder2-open",
        "sort_order": 2,
    },
    {
        "code": "reports.manufacturing",
        "name": "Manufacturing Reports",
        "parent_code": "reports",
        "route_name": "reports-manufacturing",
        "icon": "factory",
        "sort_order": 6,
    },
)


REPARENT_SPECS = (
    {
        "code": "reports.financial_hub.receivables_hub",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.customer_outstanding",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.receivable_aging",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.receivable_aging_detail",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.customer_ledger_statement",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.overdue_customers",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.credit_exposure",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.receivables_exception_report",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.open_items",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.collections_history",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.receivables_hub.sales_register",
        "parent_code": "reports.receivables",
        "metadata": {"canonical_section": "reports.receivables"},
    },
    {
        "code": "reports.financial_hub.controls_phase_one",
        "parent_code": "reports.controls",
        "metadata": {"canonical_section": "reports.controls"},
    },
    {
        "code": "reports.gstreport",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.gstr1report",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.gstr3breport",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.gstr9report",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.tdsreport",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.tcsledgerreport",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.tcsfilingpack",
        "parent_code": "reports.compliance",
        "metadata": {"canonical_section": "reports.compliance"},
    },
    {
        "code": "reports.financial_hub.posting_setup",
        "parent_code": "reports.controls",
        "metadata": {"canonical_section": "reports.controls"},
    },
    {
        "code": "reports.financial_hub.year_end_close",
        "parent_code": "reports.controls",
        "metadata": {"canonical_section": "reports.controls"},
    },
    {
        "code": "reports.inventory.manufacturing_hub",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.inventory.manufacturing_summary",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.inventory.manufacturing_material_consumption",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.inventory.manufacturing_output_yield",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.inventory.manufacturing_posting_audit",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.inventory.manufacturing_wip_cost_summary",
        "parent_code": "reports.manufacturing",
        "metadata": {"canonical_section": "reports.manufacturing"},
    },
    {
        "code": "reports.fixed-asset-register",
        "parent_code": "reports.assets",
        "metadata": {"canonical_section": "reports.assets"},
    },
    {
        "code": "reports.depreciation-schedule",
        "parent_code": "reports.assets",
        "metadata": {"canonical_section": "reports.assets"},
    },
    {
        "code": "reports.asset-events",
        "parent_code": "reports.assets",
        "metadata": {"canonical_section": "reports.assets"},
    },
    {
        "code": "reports.asset-history",
        "parent_code": "reports.assets",
        "metadata": {"canonical_section": "reports.assets"},
    },
)


CANONICAL_ROUTE_UPDATES = {
    "reports.vendoroutstanding": {
        "route_path": "/reports/payables/vendor_outstanding",
        "route_name": "reports-payables-vendor-outstanding",
    },
    "reports.accountspayableaging": {
        "route_path": "/reports/payables/ap_aging",
        "route_name": "reports-payables-ap-aging",
    },
    "reports.vendorledgerstatement": {
        "route_path": "/reports/payables/vendor_ledger_statement",
        "route_name": "reports-payables-vendor-ledger-statement",
    },
    "reports.payablesclosepack": {
        "route_path": "/reports/payables/payables_close_pack",
        "route_name": "reports-payables-close-pack",
    },
    "reports.payables.purchase_register": {
        "route_path": "/reports/payables/purchase-register",
        "route_name": "reports-payables-purchase-register",
    },
}


LEGACY_MENU_REPLACEMENTS = {
    "reports.outstandingreport": "reports.financial_hub.receivables_hub.customer_outstanding",
    "reports.accountsreceivableaging": "reports.financial_hub.receivables_hub.receivable_aging",
    "reports.reports.purchaseregister": "reports.payables.purchase_register",
    "reports.stockledgersummary": "reports.inventory.stock_summary",
    "reports.stockledgerbook": "reports.inventory.stock_ledger",
    "reports.stockdaybook": "reports.inventory.stock_day_book",
    "reports.inventory.stockdaybook": "reports.inventory.stock_day_book",
    "reports.stockbookreport": "reports.inventory.stock_book_detail",
    "reports.inventory.stockbookreport": "reports.inventory.stock_book_detail",
    "reports.stockbooksummary": "reports.inventory.stock_book_summary",
    "reports.inventory.stockbooksummary": "reports.inventory.stock_book_summary",
    "reports.stockmovementreport": "reports.inventory.stock_movement",
    "reports.inventory.stockmovementreport": "reports.inventory.stock_movement",
    "reports.stockagingreport": "reports.inventory.stock_aging",
    "reports.inventory.stockagingreport": "reports.inventory.stock_aging",
}


def _ensure_group(Menu, spec):
    parent = Menu.objects.filter(code=spec["parent_code"]).first()
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
                "seed": "report_section_normalization",
                "catalog_version": CATALOG_VERSION,
                "menu_code": spec["code"],
                "section": True,
            },
            "isactive": True,
        },
    )
    return menu


def _merge_metadata(menu, extra):
    metadata = dict(menu.metadata or {})
    metadata.update(extra)
    return metadata


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    for spec in SECTION_GROUP_SPECS:
        _ensure_group(Menu, spec)

    for spec in REPARENT_SPECS:
        menu = Menu.objects.filter(code=spec["code"]).first()
        parent = Menu.objects.filter(code=spec["parent_code"]).first()
        if menu is None or parent is None:
            continue
        menu.parent_id = parent.id
        menu.isactive = True
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_section_normalization",
                "catalog_version": CATALOG_VERSION,
                **spec["metadata"],
            },
        )
        menu.save(update_fields=["parent_id", "isactive", "metadata", "updated_at"])

    for code, route_config in CANONICAL_ROUTE_UPDATES.items():
        menu = Menu.objects.filter(code=code).first()
        if menu is None:
            continue
        menu.route_path = route_config["route_path"]
        menu.route_name = route_config["route_name"]
        menu.isactive = True
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_section_normalization",
                "catalog_version": CATALOG_VERSION,
                "canonical_route": route_config["route_path"],
            },
        )
        menu.save(update_fields=["route_path", "route_name", "isactive", "metadata", "updated_at"])

    for legacy_code, replacement_code in LEGACY_MENU_REPLACEMENTS.items():
        menu = Menu.objects.filter(code=legacy_code).first()
        if menu is None:
            continue
        menu.isactive = False
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_section_normalization",
                "catalog_version": CATALOG_VERSION,
                "legacy": True,
                "replaced_by": replacement_code,
            },
        )
        menu.save(update_fields=["isactive", "metadata", "updated_at"])

    # Keep any old visibility relations but disable them on deactivated menus so
    # only the canonical sectioned entries remain menu-visible.
    legacy_menu_ids = list(
        Menu.objects.filter(code__in=tuple(LEGACY_MENU_REPLACEMENTS.keys())).values_list("id", flat=True)
    )
    if legacy_menu_ids:
        MenuPermission.objects.filter(
            menu_id__in=legacy_menu_ids,
            relation_type=MENU_RELATION_VISIBILITY,
        ).update(isactive=False)


def backwards(apps, schema_editor):
    # Forward-only normalization. Reversal would risk reactivating legacy menus in
    # live tenants after the canonical tree has been adopted.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0099_reconcile_financial_report_routes"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
