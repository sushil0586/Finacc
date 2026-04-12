from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_stock_ledger_menu_2026_04_12"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code="reports.inventory", isactive=True).first()
    if parent_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code="reports.inventory.stock_ledger",
        defaults={
            "parent_id": parent_menu.id,
            "name": "Stock Ledger",
            "menu_type": "screen",
            "route_path": "/reports/inventory/stock-ledger",
            "route_name": "inventory-stock-ledger",
            "icon": "book-open",
            "sort_order": 3,
            "is_system_menu": True,
            "metadata": {
                "seed": "inventory_stock_ledger_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.inventory.stock_ledger",
                "permission_code": "reports.inventory.stock_ledger.view",
            },
            "isactive": True,
        },
    )

    permission, _ = Permission.objects.update_or_create(
        code="reports.inventory.stock_ledger.view",
        defaults={
            "name": "Reports Inventory Stock Ledger View",
            "module": "reports",
            "resource": "inventory",
            "action": "view",
            "description": "Reports Inventory Stock Ledger View",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "inventory_stock_ledger_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": "reports.inventory.stock_ledger",
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

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", "permission_id")
    )
    rows = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            metadata={"seed": "inventory_stock_ledger_menu", "catalog_version": CATALOG_VERSION},
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

    permission_ids = list(Permission.objects.filter(code="reports.inventory.stock_ledger.view").values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code="reports.inventory.stock_ledger").values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0047_fix_inventory_report_menu_seed")]

    operations = [migrations.RunPython(forwards, backwards)]
