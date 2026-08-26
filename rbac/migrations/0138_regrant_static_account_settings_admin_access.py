from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "static_account_settings_admin_access_regrant"
CATALOG_VERSION = "static_account_settings_admin_access_regrant_2026_08_25"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSION_SPECS = (
    ("posting.static_account_settings.view", "View Static Account Settings", "view"),
    ("posting.static_account_settings.create", "Create Static Account Mapping", "create"),
    ("posting.static_account_settings.edit", "Edit Static Account Mapping", "edit"),
    ("posting.static_account_settings.update", "Update Static Account Mapping", "update"),
    ("posting.static_account_settings.delete", "Delete Static Account Mapping", "delete"),
    ("posting.static_account_settings.validate", "Validate Static Account Mapping", "validate"),
    ("posting.static_account_settings.bulk_upsert", "Bulk Upsert Static Account Mapping", "bulk_upsert"),
)


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "posting",
                "resource": "static_account_settings",
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids or not permission_ids:
        return

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=role_ids,
            permission_id__in=permission_ids,
        ).values_list("role_id", "permission_id")
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
                    metadata={
                        "seed": SEED_TAG,
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0137_add_inventory_adjustment_action_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
