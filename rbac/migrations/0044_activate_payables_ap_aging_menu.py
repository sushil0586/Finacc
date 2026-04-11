from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "payables_ap_aging_menu_2026_04_10"


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
        code="reports.accountspayableaging",
        defaults={
            "parent_id": parent_menu.id,
            "name": "AP Aging",
            "menu_type": "screen",
            "route_path": "/reports/payables/ap_aging",
            "route_name": "accountspayableaging",
            "icon": "timer",
            "sort_order": 2,
            "is_system_menu": True,
            "metadata": {
                "seed": "payables_ap_aging_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.accountspayableaging",
                "report_code": "ap_aging",
                "permission_code": "reports.accountspayableaging.view",
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code="reports.accountspayableaging.view", isactive=True).first()
    if permission:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0043_fix_assignment_effective_datetime_types")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
