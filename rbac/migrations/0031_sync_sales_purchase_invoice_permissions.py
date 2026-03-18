from django.db import migrations

ROLE_PERMISSION_ALLOW = "allow"
TARGET_PERMISSIONS = [
    # Sales invoice
    "sales.invoice.create",
    "sales.invoice.edit",
    "sales.invoice.update",
    "sales.invoice.cancel",
    "sales.invoice.post",
    "sales.invoice.confirm",
    "sales.invoice.view",
    # Purchase invoice
    "purchase.invoice.create",
    "purchase.invoice.edit",
    "purchase.invoice.update",
    "purchase.invoice.cancel",
    "purchase.invoice.post",
    "purchase.invoice.confirm",
    "purchase.invoice.view",
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code__in=TARGET_PERMISSIONS, isactive=True).values_list("id", flat=True))
    if not permission_ids:
        return

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    if not role_ids:
        return

    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )

    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    isactive=True,
                    metadata={"seed": "invoice_permission_sync"},
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code__in=TARGET_PERMISSIONS).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed="invoice_permission_sync").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0030_add_cash_bank_journal_voucher_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
