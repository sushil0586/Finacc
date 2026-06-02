from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_SPEC = {
    "code": "reports.payables.msme_overdue",
    "report_code": "msme_overdue",
    "name": "MSME Overdue Report",
    "route_path": "/reports/payables/msme_overdue",
    "route_name": "reports-payables-msme-overdue",
    "icon": "building-2",
    "sort_order": 4,
    "permission_code": "reports.payables.view",
}


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    parent_menu = Menu.objects.filter(code="reports.payables").first()
    if not parent_menu:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": MENU_SPEC["name"],
            "menu_type": "screen",
            "route_path": MENU_SPEC["route_path"],
            "route_name": MENU_SPEC["route_name"],
            "icon": MENU_SPEC["icon"],
            "sort_order": MENU_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "msme_overdue_payables_menu",
                "menu_code": MENU_SPEC["code"],
                "report_code": MENU_SPEC["report_code"],
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code=MENU_SPEC["permission_code"], isactive=True).first()
    if permission:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0123_merge_gst_reconciliation_workspace_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
