from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "legacy_invoice_import_menus_2026_05_14"

MENU_SPECS = (
    {
        "code": "sales.sales-legacy-import",
        "name": "Legacy Import",
        "parent_codes": ["sales"],
        "route_path": "sales-legacy-import",
        "route_name": "sales-legacy-import",
        "icon": "cloud-upload",
        "sort_order": 8,
        "permission_code": "sales.invoice.view",
        "feature": "feature_sales",
        "menu_group": "sales",
    },
    {
        "code": "purchase.purchase-legacy-import",
        "name": "Legacy Import",
        "parent_codes": ["purchase"],
        "route_path": "purchase-legacy-import",
        "route_name": "purchase-legacy-import",
        "icon": "cloud-upload",
        "sort_order": 4,
        "permission_code": "purchase.invoice.view",
        "feature": "feature_purchase",
        "menu_group": "purchase",
    },
)


def _resolve_parent(Menu, parent_codes):
    for code in parent_codes:
        parent = Menu.objects.filter(code=code, isactive=True).first()
        if parent:
            return parent
    return None


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    for spec in MENU_SPECS:
        parent = _resolve_parent(Menu, spec["parent_codes"])
        if parent is None:
            continue

        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "legacy_invoice_import_menus",
                    "catalog_version": CATALOG_VERSION,
                    "feature": spec["feature"],
                    "access_mode": "operational",
                    "route": spec["route_path"],
                    "menu_group": spec["menu_group"],
                },
                "isactive": True,
            },
        )

        permission = Permission.objects.filter(code=spec["permission_code"], isactive=True).first()
        if permission is None:
            continue

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0112_add_new_payables_reports_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
