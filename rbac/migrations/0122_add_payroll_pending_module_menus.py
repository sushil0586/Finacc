from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
SEED_TAG = "payroll_pending_module_menus"
CATALOG_VERSION = "payroll_pending_module_menus_2026_05_17"


SCREEN_SPECS = (
    {
        "menu_code": "payroll.contract-tax-declarations",
        "name": "Contract Tax Declarations",
        "route_path": "/payroll/contract-tax-declarations",
        "route_name": "payroll-contract-tax-declarations",
        "icon": "receipt-text",
        "sort_order": 14,
        "permission_code": "payroll.contract_profile.view",
    },
    {
        "menu_code": "payroll.contract-input-snapshots",
        "name": "Contract Input Snapshots",
        "route_path": "/payroll/contract-input-snapshots",
        "route_name": "payroll-contract-input-snapshots",
        "icon": "database-zap",
        "sort_order": 15,
        "permission_code": "payroll.contract_profile.view",
    },
    {
        "menu_code": "payroll.approval-policies",
        "name": "Approval Policies",
        "route_path": "/payroll/approval-policies",
        "route_name": "payroll-approval-policies",
        "icon": "badge-check",
        "sort_order": 18,
        "permission_code": "payroll.policies.view",
    },
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    root_menu = Menu.objects.get(code="payroll")

    for spec in SCREEN_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["menu_code"],
            defaults={
                "parent_id": root_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "route_path": spec["route_path"],
                    "feature": "feature_payroll",
                    "access_mode": "setup",
                    "menu_group": "payroll",
                },
                "isactive": True,
            },
        )
        permission = Permission.objects.get(code=spec["permission_code"])
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    menu_codes = [spec["menu_code"] for spec in SCREEN_SPECS]
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))
    if menu_ids:
        MenuPermission.objects.filter(menu_id__in=menu_ids, relation_type=MENU_RELATION_VISIBILITY).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0121_add_payroll_attendance_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
