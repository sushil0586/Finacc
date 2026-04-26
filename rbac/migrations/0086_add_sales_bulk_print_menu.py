from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "sales_bulk_print_menu_2026_04_26"

MENU_SPEC = {
    "code": "sales.sales-bulk-print-center",
    "name": "Bulk Print Center",
    "parent_codes": ["sales"],
    "route_path": "sales-bulk-print-center",
    "route_name": "sales-bulk-print-center",
    "icon": "printer",
    "sort_order": 7,
    "permission_code": "sales.invoice.view",
}


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

    parent = _resolve_parent(Menu, MENU_SPEC["parent_codes"])
    if parent is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": parent.id,
            "name": MENU_SPEC["name"],
            "menu_type": "screen",
            "route_path": MENU_SPEC["route_path"],
            "route_name": MENU_SPEC["route_name"],
            "icon": MENU_SPEC["icon"],
            "sort_order": MENU_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "sales_bulk_print_menu",
                "catalog_version": CATALOG_VERSION,
                "feature": "feature_sales",
                "access_mode": "operational",
                "route": MENU_SPEC["route_path"],
                "menu_group": "sales",
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code=MENU_SPEC["permission_code"], isactive=True).first()
    if permission is None:
        return

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )


def backwards(apps, schema_editor):
    # Keep forward-only to avoid removing menus from live setups.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0085_reconcile_purchase_invoice_workflow_admin_roles"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
