from django.db import migrations

PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "frontend_permission_catalog_2026_03"

NEW_PERMISSIONS = [
    # Cash Voucher
    ("voucher.cashvoucher.create", "Create Cash Voucher", "voucher", "cashvoucher", "create"),
    ("voucher.cashvoucher.edit", "Edit Cash Voucher", "voucher", "cashvoucher", "edit"),
    ("voucher.cashvoucher.update", "Update Cash Voucher", "voucher", "cashvoucher", "update"),
    # Bank Voucher
    ("voucher.bankvoucher.create", "Create Bank Voucher", "voucher", "bankvoucher", "create"),
    ("voucher.bankvoucher.edit", "Edit Bank Voucher", "voucher", "bankvoucher", "edit"),
    ("voucher.bankvoucher.update", "Update Bank Voucher", "voucher", "bankvoucher", "update"),
    # Journal Voucher
    ("voucher.journalvoucher.create", "Create Journal Voucher", "voucher", "journalvoucher", "create"),
    ("voucher.journalvoucher.edit", "Edit Journal Voucher", "voucher", "journalvoucher", "edit"),
    ("voucher.journalvoucher.update", "Update Journal Voucher", "voucher", "journalvoucher", "update"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")

    for code, name, module, resource, action in NEW_PERMISSIONS:
        Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION, "kind": "addon"},
                "isactive": True,
            },
        )


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.filter(code__in=[code for code, *_ in NEW_PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0028_parent_only_payables_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
