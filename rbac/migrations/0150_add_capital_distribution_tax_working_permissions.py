from django.db import migrations


SEED_TAG = "capital_distribution_phase6_tax_working_permissions"
CATALOG_VERSION = "capital_distribution_phase6_tax_working_2026_09_11"
ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSIONS = (
    ("capital_distribution.tax_working.view", "View Appropriation Tax Workings", "tax_working", "view"),
    ("capital_distribution.tax_working.calculate", "Calculate Appropriation Tax Workings", "tax_working", "calculate"),
    ("capital_distribution.tax_working.override", "Override Appropriation Tax Workings", "tax_working", "override"),
    ("capital_distribution.tax_working.submit", "Submit Appropriation Tax Workings", "tax_working", "submit"),
    ("capital_distribution.tax_working.approve", "Approve Appropriation Tax Workings", "tax_working", "approve"),
    ("capital_distribution.tax_working.reverse", "Reverse Appropriation Tax Workings", "tax_working", "reverse"),
)


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = []
    for code, name, resource, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "capital_distribution",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True)
    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    RolePermission.objects.bulk_create([
        RolePermission(
            role_id=role_id,
            permission_id=permission_id,
            effect="allow",
            metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
            isactive=True,
        )
        for role_id in role_ids
        for permission_id in permission_ids
        if (role_id, permission_id) not in existing
    ])


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = list(
        Permission.objects.filter(
            code__in=[row[0] for row in PERMISSIONS],
            metadata__seed=SEED_TAG,
        ).values_list("id", flat=True)
    )
    RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0149_add_capital_distribution_tax_policy_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
