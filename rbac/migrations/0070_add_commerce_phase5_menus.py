from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "commerce_phase5_menu_2026_04_18"
SEED_TAG = "commerce_phase5_menu_seed"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


MENU_SPECS = [
    {
        "code": "sales.commerce_line_tester",
        "name": "Commerce Line Tester",
        "parent_code": "sales",
        "route_path": "/commerce-line-tester",
        "route_name": "commerce-line-tester",
        "icon": "scan-line",
        "sort_order": 3,
        "permission_code": "commerce.line_tester.view",
    },
    {
        "code": "admin.commerce_promotions",
        "name": "Commerce Promotions",
        "parent_code": "admin.configuration",
        "route_path": "/commerce-promotions",
        "route_name": "commerce-promotions",
        "icon": "badge-percent",
        "sort_order": 4,
        "permission_code": "commerce.promotion.view",
    },
]


PERMISSION_SPECS = [
    ("commerce.line_tester.view", "commerce", "line_tester", "view", "View Commerce Line Tester"),
    ("commerce.promotion.view", "commerce", "promotion", "view", "View Commerce Promotions"),
    ("commerce.promotion.create", "commerce", "promotion", "create", "Create Commerce Promotions"),
    ("commerce.promotion.update", "commerce", "promotion", "update", "Update Commerce Promotions"),
    ("commerce.promotion.delete", "commerce", "promotion", "delete", "Delete Commerce Promotions"),
]


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
        for code, module, resource, action, name in PERMISSION_SPECS
    }

    for spec in MENU_SPECS:
        parent_menu = Menu.objects.filter(code=spec["parent_code"], isactive=True).first()
        if parent_menu is None:
            continue

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
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission = permission_by_code[spec["permission_code"]]
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    role_ids = list(
        Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
    )
    permission_ids = [permission.id for permission in permission_by_code.values()]
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
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

    permission_codes = [row[0] for row in PERMISSION_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    Menu.objects.filter(code__in=[spec["code"] for spec in MENU_SPECS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0069_add_manufacturing_route_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
