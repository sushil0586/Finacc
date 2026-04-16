from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
CATALOG_VERSION = "inventory_transfer_browser_menu_2026_04_16"


MENU_SPEC = {
    "menu_code": "reports.inventory.transfer_browser",
    "name": "Transfer Browser",
    "route_path": "/inventory-transfer-list",
    "route_name": "inventory-transfer-list",
    "icon": "list-ul",
    "sort_order": 4,
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
                "seed": "inventory_transfer_browser_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["menu_code"],
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission = Permission.objects.filter(code=MENU_SPEC["permission_code"]).first()
    if permission is None:
        return

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True)
        .values_list("id", flat=True)
    )
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id)
        .values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        if (role_id, permission.id) in existing_pairs:
            continue
        rows.append(
            RolePermission(
                role_id=role_id,
                permission_id=permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": "inventory_transfer_browser_menu", "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
        )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.filter(code=MENU_SPEC["menu_code"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0060_add_posting_setup_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
