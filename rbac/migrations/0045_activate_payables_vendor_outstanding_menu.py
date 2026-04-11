from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "payables_vendor_outstanding_menu_2026_04_10"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    parent_menu = (
        Menu.objects.filter(code="reports.reports.payables").first()
        or Menu.objects.filter(code="reports.payables").first()
    )
    if parent_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code="reports.vendoroutstanding",
        defaults={
            "parent_id": parent_menu.id,
            "name": "Vendor Outstanding Report",
            "menu_type": "screen",
            "route_path": "/reports/payables/vendor_outstanding",
            "route_name": "vendoroutstanding",
            "icon": "wallet-minimal",
            "sort_order": 1,
            "is_system_menu": True,
            "metadata": {
                "seed": "payables_vendor_outstanding_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.vendoroutstanding",
                "report_code": "vendor_outstanding",
                "permission_code": "reports.vendoroutstanding.view",
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code="reports.vendoroutstanding.view", isactive=True).first()
    if permission:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0044_activate_payables_ap_aging_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
