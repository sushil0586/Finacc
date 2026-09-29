from django.db import migrations


ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "hrms_attendance_runtime_superadmin_2026_09_26"

PERMISSION_CODES = (
    "hrms.attendance_entry.view",
    "hrms.attendance_entry.create",
    "hrms.attendance_entry.update",
    "hrms.attendance_import_batch.view",
    "hrms.attendance_import_batch.create",
    "hrms.attendance_payroll_period.view",
    "hrms.attendance_summary.view",
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
    dependencies = [("rbac", "0201_activate_hrms_leave_runtime_superadmin")]

    operations = [migrations.RunPython(forwards, backwards)]
