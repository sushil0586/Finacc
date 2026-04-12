from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_report_menu_fix_2026_04_12"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    legacy_hub = Menu.objects.filter(code="reports.inventory.hub").first()
    if legacy_hub is not None:
        legacy_hub.delete()

    reports_parent = Menu.objects.filter(code="reports", isactive=True).first()
    if reports_parent is None:
        reports_parent = Menu.objects.filter(code="reports.reports", isactive=True).first()

    inventory_menu, _ = Menu.objects.update_or_create(
        code="reports.inventory",
        defaults={
            "parent_id": reports_parent.id if reports_parent else None,
            "name": "Inventory Hub",
            "menu_type": "screen",
            "route_path": "/reports/inventory",
            "route_name": "inventoryhub",
            "icon": "boxes",
            "sort_order": 20,
            "is_system_menu": True,
            "metadata": {
                "seed": "inventory_report_menu_fix",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.inventory",
                "report_code": "inventory_hub",
                "permission_code": "reports.inventory.view",
            },
            "isactive": True,
        },
    )

    menu_specs = [
        {
            "code": "reports.inventory.stock_summary",
            "name": "Stock Summary",
            "route_path": "/reports/inventory/stock-summary",
            "route_name": "inventory-stock-summary",
            "icon": "summary",
            "sort_order": 1,
            "permission_code": "reports.inventory.stock_summary.view",
        },
    ]

    permission_ids = []
    for spec in menu_specs:
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": inventory_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "inventory_report_menu_fix",
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
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "inventory_report_menu_fix",
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

    root_permission, _ = Permission.objects.update_or_create(
        code="reports.inventory.view",
        defaults={
            "name": "Reports Inventory View",
            "module": "reports",
            "resource": "inventory",
            "action": "view",
            "description": "Reports Inventory View",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "inventory_report_menu_fix",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.inventory",
            },
            "isactive": True,
        },
    )
    MenuPermission.objects.update_or_create(
        menu_id=inventory_menu.id,
        permission_id=root_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )
    permission_ids.append(root_permission.id)

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True).values_list("id", flat=True)
    )
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "inventory_report_menu_fix", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [
        "reports.inventory.view",
        "reports.inventory.stock_summary.view",
    ]
    permissions = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permissions:
        RolePermission.objects.filter(permission_id__in=permissions).delete()
        MenuPermission.objects.filter(permission_id__in=permissions).delete()
        Permission.objects.filter(id__in=permissions).delete()

    Menu.objects.filter(code__in=["reports.inventory", "reports.inventory.stock_summary"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0046_add_inventory_report_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
