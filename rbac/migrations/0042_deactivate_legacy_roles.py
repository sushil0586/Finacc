from django.db import migrations


CURRENT_ROLE_CODES = {
    "entity.super_admin",
    "admin",
    "manager",
    "accountant",
    "sales_user",
    "purchase_user",
    "accounts_user",
    "report_viewer",
    "payroll_user",
    "compliance_user",
}


def forwards(apps, schema_editor):
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    UserRoleAssignment = apps.get_model("rbac", "UserRoleAssignment")

    legacy_role_ids = list(
        Role.objects.filter(isactive=True).exclude(code__in=CURRENT_ROLE_CODES).values_list("id", flat=True)
    )
    if not legacy_role_ids:
        return

    UserRoleAssignment.objects.filter(role_id__in=legacy_role_ids, isactive=True).update(
        is_primary=False,
        isactive=False,
    )
    RolePermission.objects.filter(role_id__in=legacy_role_ids, isactive=True).update(isactive=False)
    Role.objects.filter(id__in=legacy_role_ids, isactive=True).update(isactive=False, is_assignable=False)


def backwards(apps, schema_editor):
    # This cleanup intentionally retires legacy role records. Reactivation, if
    # ever needed, should be done manually after a deliberate review.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0041_deactivate_legacy_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
