from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "static_account_settings_menu_2026_03_18"

MENU_CODE = "admin.static-account-settings"
PARENT_MENU_CODE = "admin"

PERMISSIONS = [
    ("posting.static_account_settings.view", "View Static Account Settings", "posting", "static_account_settings", "view"),
    ("posting.static_account_settings.create", "Create Static Account Mapping", "posting", "static_account_settings", "create"),
    ("posting.static_account_settings.edit", "Edit Static Account Mapping", "posting", "static_account_settings", "edit"),
    ("posting.static_account_settings.update", "Update Static Account Mapping", "posting", "static_account_settings", "update"),
    ("posting.static_account_settings.delete", "Delete Static Account Mapping", "posting", "static_account_settings", "delete"),
    ("posting.static_account_settings.validate", "Validate Static Account Mapping", "posting", "static_account_settings", "validate"),
    ("posting.static_account_settings.bulk_upsert", "Bulk Upsert Static Account Mapping", "posting", "static_account_settings", "bulk_upsert"),
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code=PARENT_MENU_CODE).first()
    menu, _ = Menu.objects.update_or_create(
        code=MENU_CODE,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "Static Account Settings",
            "menu_type": "screen",
            "route_path": "static-account-settings",
            "route_name": "static-account-settings",
            "icon": "settings-2",
            "sort_order": 18,
            "is_system_menu": True,
            "metadata": {
                "seed": "static_account_settings_menu",
                "catalog_version": CATALOG_VERSION,
                "module": "posting",
            },
            "isactive": True,
        },
    )

    permission_ids = []
    permission_by_code = {}
    for code, name, module, resource, action in PERMISSIONS:
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
                    "seed": "static_account_settings_menu",
                    "catalog_version": CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        permission_by_code[code] = permission

    view_permission = permission_by_code["posting.static_account_settings.view"]
    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=view_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )
    if not role_ids:
        return

    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list(
            "role_id", "permission_id"
        )
    )
    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={
                        "seed": "static_account_settings_menu",
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [code for code, *_ in PERMISSIONS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code=MENU_CODE).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(
            permission_id__in=permission_ids,
            metadata__seed="static_account_settings_menu",
        ).delete()
        MenuPermission.objects.filter(menu_id__in=menu_ids, permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0031_sync_sales_purchase_invoice_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
