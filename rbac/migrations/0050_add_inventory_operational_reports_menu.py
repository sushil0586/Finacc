from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_operational_reports_menu_2026_04_12"


REPORT_SPECS = [
    {
        "menu_code": "reports.inventory.stock_movement",
        "name": "Stock Movement",
        "route_path": "/reports/inventory/stock-movement",
        "route_name": "inventory-stock-movement",
        "icon": "shuffle",
        "sort_order": 5,
        "permission_code": "reports.inventory.stock_movement.view",
    },
    {
        "menu_code": "reports.inventory.stock_day_book",
        "name": "Stock Day Book",
        "route_path": "/reports/inventory/stock-day-book",
        "route_name": "inventory-stock-day-book",
        "icon": "calendar-day",
        "sort_order": 6,
        "permission_code": "reports.inventory.stock_day_book.view",
    },
    {
        "menu_code": "reports.inventory.stock_book_summary",
        "name": "Stock Book Summary",
        "route_path": "/reports/inventory/stock-book-summary",
        "route_name": "inventory-stock-book-summary",
        "icon": "journal-text",
        "sort_order": 7,
        "permission_code": "reports.inventory.stock_book_summary.view",
    },
    {
        "menu_code": "reports.inventory.stock_book_detail",
        "name": "Stock Book Detail",
        "route_path": "/reports/inventory/stock-book-detail",
        "route_name": "inventory-stock-book-detail",
        "icon": "list-task",
        "sort_order": 8,
        "permission_code": "reports.inventory.stock_book_detail.view",
    },
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code="reports.inventory", isactive=True).first()
    if parent_menu is None:
        return

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True).values_list("id", flat=True))

    for spec in REPORT_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["menu_code"],
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
                    "seed": "inventory_operational_reports_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission, _ = Permission.objects.update_or_create(
            code=spec["permission_code"],
            defaults={
                "name": f"Reports Inventory {spec['name']} View",
                "module": "reports",
                "resource": "inventory",
                "action": "view",
                "description": f"Reports Inventory {spec['name']} View",
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "inventory_operational_reports_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                },
                "isactive": True,
            },
        )

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        existing_pairs = set(
            RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", "permission_id")
        )
        rows = [
            RolePermission(
                role_id=role_id,
                permission_id=permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": "inventory_operational_reports_menu", "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in role_ids
            if (role_id, permission.id) not in existing_pairs
        ]
        if rows:
            RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [spec["permission_code"] for spec in REPORT_SPECS]
    menu_codes = [spec["menu_code"] for spec in REPORT_SPECS]

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0049_add_inventory_stock_aging_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
