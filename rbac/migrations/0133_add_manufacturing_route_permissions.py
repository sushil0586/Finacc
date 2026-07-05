from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "manufacturing_route_permission_seed"
CATALOG_VERSION = "manufacturing_route_permission_2026_07_04"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

ROUTE_PERMISSION_SPECS = [
    ("manufacturing.route.view", "manufacturing", "route", "view", "View Manufacturing Route"),
    ("manufacturing.route.create", "manufacturing", "route", "create", "Create Manufacturing Route"),
    ("manufacturing.route.update", "manufacturing", "route", "update", "Update Manufacturing Route"),
    ("manufacturing.route.delete", "manufacturing", "route", "delete", "Delete Manufacturing Route"),
]

ROUTE_MENU_CODES = (
    "inventory.manufacturing_routes",
    "reports.inventory.manufacturing_routes",
)


def _upsert_permission(Permission, code: str, module: str, resource: str, action: str, name: str):
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "module": module,
            "resource": resource,
            "action": action,
            "description": name,
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": code,
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

    permission_by_code = {
        code: _upsert_permission(Permission, code, module, resource, action, name)
        for code, module, resource, action, name in ROUTE_PERMISSION_SPECS
    }

    route_view_permission = permission_by_code["manufacturing.route.view"]
    menus = Menu.objects.filter(code__in=ROUTE_MENU_CODES, isactive=True)
    for menu in menus:
        metadata = dict(menu.metadata or {})
        metadata["permission_code"] = "manufacturing.route.view"
        metadata["catalog_version"] = CATALOG_VERSION
        metadata["seed"] = SEED_TAG
        menu.metadata = metadata
        menu.save(update_fields=["metadata"])
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=route_view_permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    permission_ids = [permission.id for permission in permission_by_code.values()]
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
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
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

    permission_codes = [row[0] for row in ROUTE_PERMISSION_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))

    menus = Menu.objects.filter(code__in=ROUTE_MENU_CODES, isactive=True)
    legacy_permission = Permission.objects.filter(code="manufacturing.bom.view", isactive=True).first()
    for menu in menus:
        metadata = dict(menu.metadata or {})
        metadata["permission_code"] = "manufacturing.bom.view"
        menu.metadata = metadata
        menu.save(update_fields=["metadata"])
        if legacy_permission is not None:
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=legacy_permission.id,
                relation_type=MENU_RELATION_VISIBILITY,
                defaults={"isactive": True},
            )

    if permission_ids:
        MenuPermission.objects.filter(permission_id__in=permission_ids, menu__code__in=ROUTE_MENU_CODES).delete()
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0132_add_tcs_compliance_center_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
