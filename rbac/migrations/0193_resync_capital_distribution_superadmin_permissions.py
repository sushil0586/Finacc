from django.db import migrations


ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "capital_distribution_superadmin_resync_2026_09_25"

PERMISSION_CODES = (
    "capital_distribution.setup.view",
    "capital_distribution.setup.manage",
    "capital_distribution.migration.view",
    "capital_distribution.migration.manage",
    "capital_distribution.policy.view",
    "capital_distribution.policy.manage",
    "capital_distribution.policy.submit",
    "capital_distribution.policy.approve",
    "capital_distribution.mapping.manage",
    "capital_distribution.run.view",
    "capital_distribution.run.calculate",
    "capital_distribution.run.submit",
    "capital_distribution.run.approve",
    "capital_distribution.run.post",
    "capital_distribution.run.reverse",
    "capital_distribution.tax_policy.view",
    "capital_distribution.tax_policy.manage",
    "capital_distribution.tax_policy.submit",
    "capital_distribution.tax_policy.approve",
    "capital_distribution.tax_working.view",
    "capital_distribution.tax_working.calculate",
    "capital_distribution.tax_working.override",
    "capital_distribution.tax_working.submit",
    "capital_distribution.tax_working.approve",
    "capital_distribution.tax_working.reverse",
    "capital_distribution.tax_working.export",
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService().seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(
        Permission.objects.filter(code__in=PERMISSION_CODES, isactive=True).values_list("id", flat=True)
    )
    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    RolePermission.objects.bulk_create(
        [
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG},
                isactive=True,
            )
            for role_id in role_ids
            for permission_id in permission_ids
            if (role_id, permission_id) not in existing
        ]
    )


def backwards(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0192_add_superadmin_entity_partner_org_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
