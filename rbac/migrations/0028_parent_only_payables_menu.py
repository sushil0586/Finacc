from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "payables_parent_only_2026_03_16"

PARENT_MENU = {
    "code": "reports.payables",
    "name": "Payables Reports",
    "menu_type": "screen",
    "route_path": "/reports/payables",
    "route_name": "reports-payables",
    "icon": "wallet-minimal",
    "sort_order": 13,
}

PARENT_PERMISSION_CODES = (
    "reports.vendoroutstanding.view",
    "reports.accountspayableaging.view",
    "reports.vendorledgerstatement.view",
    "reports.vendorsettlementhistory.view",
    "reports.vendornoteregister.view",
    "reports.vendorbalanceexceptions.view",
    "reports.apglreconciliation.view",
    "reports.payablesclosepack.view",
    "reports.purchasebook.view",
)

CHILD_MENU_CODES = (
    "reports.vendoroutstanding",
    "reports.accountspayableaging",
    "reports.vendorledgerstatement",
    "reports.vendorsettlementhistory",
    "reports.vendornoteregister",
    "reports.vendorbalanceexceptions",
    "reports.apglreconciliation",
    "reports.payablesclosepack",
    "reports.payables.payables_dashboard_summary",
    "reports.payables.purchase_register",
    "reports.payables.payables_close_validation",
    "reports.payables.payables_close_readiness_summary",
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    financial_parent = Menu.objects.filter(code="reports.financial").first() or Menu.objects.filter(code="reports").first()
    parent_menu, _ = Menu.objects.update_or_create(
        code=PARENT_MENU["code"],
        defaults={
            "parent_id": financial_parent.id if financial_parent else None,
            "name": PARENT_MENU["name"],
            "menu_type": PARENT_MENU["menu_type"],
            "route_path": PARENT_MENU["route_path"],
            "route_name": PARENT_MENU["route_name"],
            "icon": PARENT_MENU["icon"],
            "sort_order": PARENT_MENU["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "payables_parent_only",
                "catalog_version": CATALOG_VERSION,
                "menu_code": PARENT_MENU["code"],
                "is_payables_parent": True,
                "parent_only": True,
            },
            "isactive": True,
        },
    )

    permissions = Permission.objects.filter(code__in=PARENT_PERMISSION_CODES, isactive=True)
    for permission in permissions:
        MenuPermission.objects.update_or_create(
            menu_id=parent_menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    Menu.objects.filter(code__in=CHILD_MENU_CODES).update(isactive=False)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0027_group_payables_report_menus")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
