from django.db import migrations


SEED_TAG = "tcs_report_export_permissions_2026_09_13"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSIONS = (
    ("reports.tcs_workspace.export", "Export TCS Workspace", "tcs_workspace"),
    ("reports.tcs_filing_pack.export", "Export TCS Filing Pack", "tcs_filing_pack"),
    ("reports.tcs_ca_pack.export", "Export TCS CA Pack", "tcs_ca_pack"),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    menu = Menu.objects.filter(code="reports.financial_hub.tcs_compliance_center", isactive=True).first()

    for code, name, resource in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "reports",
                "resource": resource,
                "action": "export",
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
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
    dependencies = [("rbac", "0155_add_sales_ar_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
