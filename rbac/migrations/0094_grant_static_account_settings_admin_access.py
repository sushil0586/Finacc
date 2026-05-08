from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "static_account_settings_admin_access"
CATALOG_VERSION = "static_account_settings_admin_access_2026_05_07"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSION_CODES = (
    "posting.static_account_settings.view",
    "posting.static_account_settings.create",
    "posting.static_account_settings.edit",
    "posting.static_account_settings.update",
    "posting.static_account_settings.delete",
    "posting.static_account_settings.validate",
    "posting.static_account_settings.bulk_upsert",
)


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(
        Permission.objects.filter(code__in=PERMISSION_CODES, isactive=True).values_list("id", flat=True)
    )
    if not permission_ids:
        return

    role_ids = list(
        Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
    )
    if not role_ids:
        return

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
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0093_add_manufacturing_operate_permission"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
