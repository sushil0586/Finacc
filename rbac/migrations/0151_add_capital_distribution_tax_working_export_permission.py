from django.db import migrations


SEED_TAG = "capital_distribution_phase6_tax_working_export_permission"
CATALOG_VERSION = "capital_distribution_phase6_tax_working_export_2026_09_11"
PERMISSION_CODE = "capital_distribution.tax_working.export"
ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "Export Appropriation Tax Workings",
            "module": "capital_distribution",
            "resource": "tax_working",
            "action": "export",
            "description": "Export frozen appropriation tax workings and audit evidence.",
            "scope_type": "entity",
            "is_system_defined": True,
            "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
            "isactive": True,
        },
    )
    role_ids = Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True)
    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission=permission).values_list("role_id", flat=True)
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
    permission = Permission.objects.filter(code=PERMISSION_CODE, metadata__seed=SEED_TAG).first()
    if not permission:
        return
    RolePermission.objects.filter(permission=permission, metadata__seed=SEED_TAG).delete()
    permission.delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0150_add_capital_distribution_tax_working_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
