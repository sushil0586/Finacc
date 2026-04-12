from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
CATALOG_VERSION = "inventory_report_menu_2026_04_12"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code="reports.inventory", isactive=True).first()
    if parent_menu is None:
        parent_menu = Menu.objects.filter(code="reports.reports.inventory", isactive=True).first()
    if parent_menu is None:
        return

    menu_specs = [
        {
            "code": "reports.inventory.hub",
            "name": "Inventory Hub",
            "route_path": "/reports/inventory",
            "route_name": "inventoryhub",
            "icon": "boxes",
            "sort_order": 1,
            "permission_code": "reports.inventory.view",
        },
        {
            "code": "reports.inventory.stock_summary",
            "name": "Stock Summary",
            "route_path": "/reports/inventory/stock-summary",
            "route_name": "inventory-stock-summary",
            "icon": "summary",
            "sort_order": 2,
            "permission_code": "reports.inventory.stock_summary.view",
        },
    ]

    permission_ids = []
    for spec in menu_specs:
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "inventory_report_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission, _ = Permission.objects.update_or_create(
            code=spec["permission_code"],
            defaults={
                "name": spec["permission_code"].replace(".", " ").title(),
                "module": "reports",
                "resource": "inventory",
                "action": "view" if spec["permission_code"].endswith(".view") else "export",
                "description": spec["permission_code"].replace(".", " ").title(),
                "scope_type": Permission.SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "inventory_report_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id"))
    inserts = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "inventory_report_menu", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0045_activate_payables_vendor_outstanding_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
