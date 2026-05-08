from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "manufacturing_qc_approve_permission"
CATALOG_VERSION = "manufacturing_qc_approve_2026_05_07"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSION_CODE = "manufacturing.workorder.qc_approve"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "Approve Manufacturing QC",
            "module": "manufacturing",
            "resource": "workorder",
            "action": "qc_approve",
            "description": "Approve or reject manufacturing QC-gated operations.",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": PERMISSION_CODE,
            },
            "isactive": True,
        },
    )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        if (role_id, permission.id) in existing_pairs:
            continue
        rows.append(
            RolePermission(
                role_id=role_id,
                permission_id=permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
        )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code=PERMISSION_CODE).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0091_repair_tcs_report_route_access"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
