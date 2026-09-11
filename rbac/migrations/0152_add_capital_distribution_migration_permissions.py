from django.db import migrations


SEED_TAG = "capital_distribution_phase7_migration_permissions"
CATALOG_VERSION = "capital_distribution_phase7_2026_09_11"
PERMISSIONS = (
    (
        "capital_distribution.migration.view",
        "View Capital Distribution Migration Readiness",
        "view",
        "Review Wave 1 migration and activation readiness without changing entity data.",
    ),
    (
        "capital_distribution.migration.manage",
        "Manage Capital Distribution Migration",
        "manage",
        "Apply Wave 1 migration preparation and enable or disable an entity after readiness checks.",
    ),
)
ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    role_ids = list(Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True))
    for code, name, action, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "capital_distribution",
                "resource": "migration",
                "action": action,
                "description": description,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        existing = set(
            RolePermission.objects.filter(role_id__in=role_ids, permission=permission)
            .values_list("role_id", flat=True)
        )
        RolePermission.objects.bulk_create([
            RolePermission(
                role_id=role_id,
                permission=permission,
                effect="allow",
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in role_ids
            if role_id not in existing
        ])


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permissions = Permission.objects.filter(
        code__in=[row[0] for row in PERMISSIONS],
        metadata__seed=SEED_TAG,
    )
    RolePermission.objects.filter(permission__in=permissions, metadata__seed=SEED_TAG).delete()
    permissions.delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0151_add_capital_distribution_tax_working_export_permission")]
    operations = [migrations.RunPython(forwards, backwards)]
