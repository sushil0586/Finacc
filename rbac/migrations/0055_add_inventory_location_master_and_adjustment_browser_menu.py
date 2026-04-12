from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_location_master_menu_2026_04_12"


MENU_SPECS = [
    {
        "menu_code": "reports.inventory.location_master",
        "name": "Location Master",
        "route_path": "/inventory-location-master",
        "route_name": "inventory-location-master",
        "icon": "geo-alt",
        "sort_order": 1,
        "permission_code": "inventory.location.view",
    },
    {
        "menu_code": "reports.inventory.adjustment_browser",
        "name": "Adjustment Browser",
        "route_path": "/inventory-adjustment-list",
        "route_name": "inventory-adjustment-list",
        "icon": "clipboard-data",
        "sort_order": 5,
        "permission_code": "inventory.adjustment.view",
    },
]


def _upsert_permission(Permission, menu_code, permission_code, seed_name, resource, action, label):
    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": label,
            "module": "inventory",
            "resource": resource,
            "action": action,
            "description": label,
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": seed_name,
                "catalog_version": CATALOG_VERSION,
                "menu_code": menu_code,
            },
            "isactive": True,
        },
    )
    return permission


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

    for spec in MENU_SPECS:
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
                    "seed": "inventory_location_master_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        view_permission = _upsert_permission(
            Permission,
            spec["menu_code"],
            spec["permission_code"],
            "inventory_location_master_menu",
            "location",
            "view",
            "Inventory Location View",
        )

        extra_permissions = [view_permission]
        if spec["permission_code"] == "inventory.location.view":
            create_permission = _upsert_permission(
                Permission,
                spec["menu_code"],
                "inventory.location.create",
                "inventory_location_master_menu",
                "location",
                "create",
                "Inventory Location Create",
            )
            update_permission = _upsert_permission(
                Permission,
                spec["menu_code"],
                "inventory.location.update",
                "inventory_location_master_menu",
                "location",
                "update",
                "Inventory Location Update",
            )
            delete_permission = _upsert_permission(
                Permission,
                spec["menu_code"],
                "inventory.location.delete",
                "inventory_location_master_menu",
                "location",
                "delete",
                "Inventory Location Delete",
            )
            extra_permissions.extend([create_permission, update_permission, delete_permission])
        else:
            extra_permissions.extend([])

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=view_permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        permission_ids = [permission.id for permission in extra_permissions]
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
                        metadata={"seed": "inventory_location_master_menu", "catalog_version": CATALOG_VERSION},
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

    permission_codes = [
        "inventory.location.view",
        "inventory.location.create",
        "inventory.location.update",
        "inventory.location.delete",
    ]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    Menu.objects.filter(code__in=["reports.inventory.location_master", "reports.inventory.adjustment_browser"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0054_add_inventory_adjustment_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
