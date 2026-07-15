from django.db import migrations


SEED_TAG = "report_menu_section_normalization_v2"
CATALOG_VERSION = "report_sections_2026_07_15"


GROUP_SPECS = (
    {
        "code": "reports.financial",
        "name": "Financial Reports",
        "route_name": "reports-financial-section",
        "icon": "bar-chart-line",
        "sort_order": 1,
    },
    {
        "code": "reports.payables",
        "name": "Payables Reports",
        "route_name": "reports-payables-section",
        "icon": "wallet2",
        "sort_order": 2,
    },
    {
        "code": "reports.assets",
        "name": "Asset Reports",
        "route_name": "reports-assets-section",
        "icon": "building",
        "sort_order": 7,
    },
)


MENU_REPARENT_SPECS = (
    ("reports.financial_hub", "reports.financial", 1),
    ("reports.reports.payables", "reports.payables", 1),
    ("reports.payables.purchase_register", "reports.payables", 2),
    ("reports.reports.salesregister", "reports.receivables", 18),
    ("reports.fixedassetregister", "reports.assets", 1),
    ("reports.depreciationschedule", "reports.assets", 2),
    ("reports.assetevents", "reports.assets", 3),
    ("reports.assethistory", "reports.assets", 4),
    ("reports.assetlocationcustodian", "reports.assets", 5),
)


def _ensure_group(Menu, spec):
    root = Menu.objects.filter(code="reports", isactive=True).first()
    if root is None:
        return None

    menu, _ = Menu.objects.update_or_create(
        code=spec["code"],
        defaults={
            "parent_id": root.id,
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

    groups = {}
    for spec in GROUP_SPECS:
        group = _ensure_group(Menu, spec)
        if group is not None:
            groups[spec["code"]] = group

    for menu_code, parent_code, sort_order in MENU_REPARENT_SPECS:
        menu = Menu.objects.filter(code=menu_code, isactive=True).first()
        parent = groups.get(parent_code) or Menu.objects.filter(code=parent_code, isactive=True).first()
        if menu is None or parent is None:
            continue

        metadata = dict(menu.metadata or {})
        metadata["seed"] = SEED_TAG
        metadata["catalog_version"] = CATALOG_VERSION
        metadata["report_section"] = parent_code
        menu.parent_id = parent.id
        menu.sort_order = sort_order
        menu.metadata = metadata
        menu.save(update_fields=["parent_id", "sort_order", "metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0135_normalize_operational_menu_sections"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
