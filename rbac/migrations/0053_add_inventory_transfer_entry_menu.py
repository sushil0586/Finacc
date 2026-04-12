from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_transfer_entry_menu_2026_04_12"


MENU_SPEC = {
    "menu_code": "reports.inventory.transfer_entry",
    "name": "Transfer Entry",
    "route_path": "/inventory-transfer-entry",
    "route_name": "inventory-transfer-entry",
    "icon": "arrow-left-right",
    "sort_order": 2,
    "permission_code": "inventory.transfer.view",
}


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
        code=MENU_SPEC["menu_code"],
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
                "seed": "inventory_transfer_entry_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["menu_code"],
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    view_permission, _ = Permission.objects.update_or_create(
        code=MENU_SPEC["permission_code"],
        defaults={
            "name": "Inventory Transfer View",
            "module": "inventory",
            "resource": "transfer",
            "action": "view",
            "description": "Inventory Transfer View",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "inventory_transfer_entry_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["menu_code"],
            },
            "isactive": True,
        },
    )

    create_permission, _ = Permission.objects.update_or_create(
        code="inventory.transfer.create",
        defaults={
            "name": "Inventory Transfer Create",
            "module": "inventory",
            "resource": "transfer",
            "action": "create",
            "description": "Inventory Transfer Create",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "inventory_transfer_entry_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["menu_code"],
            },
            "isactive": True,
        },
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=view_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True).values_list("id", flat=True))
    permission_ids = [view_permission.id, create_permission.id]
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "inventory_transfer_entry_menu", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = ["inventory.transfer.view", "inventory.transfer.create"]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    Menu.objects.filter(code="reports.inventory.transfer_entry").delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0052_add_inventory_location_stock_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
