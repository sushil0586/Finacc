from django.db import migrations


SEED_TAG = "treasury_setup_permissions_2026_09_17"
CATALOG_VERSION = "treasury_setup_permissions_2026_09_17"
ROLE_PERMISSION_ALLOW = "allow"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

PERMISSIONS = (
    ("treasury.setup.view", "View Treasury Setup", "treasury", "setup", "view"),
    ("treasury.setup.update", "Update Treasury Setup", "treasury", "setup", "update"),
)

COPY_FROM = {
    "treasury.setup.view": ("posting.static_account_settings.view",),
    "treasury.setup.update": (
        "posting.static_account_settings.update",
        "posting.static_account_settings.bulk_upsert",
    ),
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

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
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_by_code[code] = permission

    target_permission_ids = [permission.id for permission in permission_by_code.values()]
    role_ids = set(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))

    source_codes = sorted({code for codes in COPY_FROM.values() for code in codes})
    source_permission_ids = list(
        Permission.objects.filter(code__in=source_codes, isactive=True).values_list("id", flat=True)
    )
    role_ids.update(
        RolePermission.objects.filter(permission_id__in=source_permission_ids, isactive=True, effect=ROLE_PERMISSION_ALLOW)
        .values_list("role_id", flat=True)
    )

    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=target_permission_ids)
        .values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in role_ids:
        for permission in permission_by_code.values():
            key = (role_id, permission.id)
            if key in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission=permission,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = list(Permission.objects.filter(code__in=[row[0] for row in PERMISSIONS]).values_list("id", flat=True))
    RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0159_add_bulk_master_action_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
