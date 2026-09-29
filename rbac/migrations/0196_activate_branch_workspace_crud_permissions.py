from django.db import migrations


ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "branch_workspace_crud_permissions_2026_09_25"

PERMISSION_CODES = (
    "admin.branch.view",
    "admin.branch.create",
    "admin.branch.update",
    "admin.branch.edit",
    "admin.branch.delete",
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(
        Permission.objects.filter(code__in=PERMISSION_CODES, isactive=True)
        .values_list("id", flat=True)
    )
    role_ids = list(
        Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True)
        .values_list("id", flat=True)
    )
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
                    metadata={"seed": SEED_TAG},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0195_add_branch_workspace_superadmin_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
