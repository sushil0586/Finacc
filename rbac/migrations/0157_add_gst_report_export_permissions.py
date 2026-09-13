from django.db import migrations


SEED_TAG = "gst_report_export_permissions_2026_09_13"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSIONS = (
    (
        "reports.gstr1_gstr3b_reconciliation.export",
        "Export GSTR-1 vs GSTR-3B Reconciliation",
        "gst_reconciliation",
        "reports.gstr1gstr3breconciliation",
    ),
    (
        "reports.gst_exception_dashboard.export",
        "Export GST Exception Dashboard",
        "gst_exception_dashboard",
        "reports.gstexceptiondashboard",
    ),
    (
        "reports.gstr9.freeze",
        "Freeze GSTR-9 Snapshot",
        "gstr9",
        "reports.gstr9report",
    ),
    (
        "reports.gstr9.file",
        "Prepare and Submit GSTR-9 Filing",
        "gstr9",
        "reports.gstr9report",
    ),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))

    for code, name, resource, menu_code in PERMISSIONS:
        action = code.rsplit(".", 1)[-1]
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "reports",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
        menu = Menu.objects.filter(code=menu_code, isactive=True).first()
        if menu:
            MenuPermission.objects.update_or_create(
                menu=menu,
                permission=permission,
                relation_type="action",
                defaults={"isactive": True},
            )
        for role_id in role_ids:
            RolePermission.objects.update_or_create(
                role_id=role_id,
                permission=permission,
                defaults={
                    "effect": "allow",
                    "metadata": {"seed": SEED_TAG},
                    "isactive": True,
                },
            )


def backwards(apps, schema_editor):
    # Preserve the live permission catalog if application code is rolled back.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0156_add_tcs_report_export_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
