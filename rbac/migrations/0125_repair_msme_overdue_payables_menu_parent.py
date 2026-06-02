from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_CODE = "reports.payables.msme_overdue"
PERMISSION_CODE = "reports.payables.view"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    parent_menu = (
        Menu.objects.filter(code="reports.payables", isactive=True).first()
        or Menu.objects.filter(code="reports.reports.payables", isactive=True).first()
    )
    if parent_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_CODE,
        defaults={
            "parent_id": parent_menu.id,
            "name": "MSME Overdue Report",
            "menu_type": "screen",
            "route_path": "/reports/payables/msme_overdue",
            "route_name": "reports-payables-msme-overdue",
            "icon": "building-2",
            "sort_order": 27,
            "is_system_menu": True,
            "metadata": {
                "seed": "repair_msme_overdue_payables_menu_parent",
                "menu_code": MENU_CODE,
                "report_code": "msme_overdue",
                "permission_code": PERMISSION_CODE,
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code=PERMISSION_CODE, isactive=True).first()
    if permission:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0124_add_msme_overdue_payables_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
