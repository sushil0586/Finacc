from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "frontend_permission_catalog_2026_03_sales_compliance"

PERMISSION_SPECS = [
    ("sales.compliance.view", "View Sales Compliance", "sales", "compliance", "view"),
    ("sales.compliance.ensure", "Ensure Sales Compliance Artifacts", "sales", "compliance", "ensure"),
    ("sales.compliance.generate_irn", "Generate Sales IRN", "sales", "compliance", "generate_irn"),
    ("sales.compliance.generate_eway", "Generate Sales E-Way", "sales", "compliance", "generate_eway"),
    ("sales.compliance.cancel_irn", "Cancel Sales IRN", "sales", "compliance", "cancel_irn"),
    ("sales.compliance.cancel_eway", "Cancel Sales E-Way", "sales", "compliance", "cancel_eway"),
    ("sales.compliance.update_eway", "Update/Extend Sales E-Way", "sales", "compliance", "update_eway"),
    ("sales.compliance.fetch", "Fetch Sales Compliance Status", "sales", "compliance", "fetch"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, module, resource, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "frontend_permission_catalog",
                    "catalog_version": CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )
    if not role_ids:
        return

    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list(
            "role_id", "permission_id"
        )
    )

    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={
                        "seed": "frontend_permission_catalog",
                        "catalog_version": CATALOG_VERSION,
                    },
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    codes = [row[0] for row in PERMISSION_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0035_add_sales_purchase_unpost_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
