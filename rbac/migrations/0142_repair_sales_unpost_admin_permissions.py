from django.db import migrations


PERMISSION_SPECS = (
    ("sales.invoice.unpost", "Unpost Sales Invoice", "invoice"),
    ("sales.credit_note.unpost", "Unpost Sales Credit Note", "credit_note"),
    ("sales.debit_note.unpost", "Unpost Sales Debit Note", "debit_note"),
)
ADMIN_ROLE_CODES = ("entity.super_admin", "admin")
CATALOG_VERSION = "sales_unpost_admin_repair_2026_09"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permissions = []
    for code, name, resource in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "sales",
                "resource": resource,
                "action": "unpost",
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permissions.append(permission)

    for role in Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True):
        for permission in permissions:
            role_permission, _ = RolePermission.objects.get_or_create(
                role_id=role.id,
                permission_id=permission.id,
                defaults={
                    "effect": "allow",
                    "metadata": {"catalog_version": CATALOG_VERSION},
                    "isactive": True,
                },
            )
            changed = False
            if role_permission.effect != "allow":
                role_permission.effect = "allow"
                changed = True
            if not role_permission.isactive:
                role_permission.isactive = True
                changed = True
            if changed:
                role_permission.save(update_fields=["effect", "isactive", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("rbac", "0141_retire_legacy_payroll_menu_aliases")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
