from django.db import migrations


SEED_TAG = "purchase_statutory_export_permission_2026_09_13"
PERMISSION_CODE = "purchase.statutory.export"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "Export Purchase Statutory Data",
            "module": "purchase",
            "resource": "statutory",
            "action": "export",
            "description": "Export purchase statutory reports, filing payloads, and certificates.",
            "scope_type": "entity",
            "is_system_defined": True,
            "metadata": {"seed": SEED_TAG},
            "isactive": True,
        },
    )
    menu = Menu.objects.filter(code="purchase.purchasestatutory", isactive=True).first()
    if menu:
        MenuPermission.objects.update_or_create(
            menu=menu,
            permission=permission,
            relation_type="action",
            defaults={"isactive": True},
        )

    role_ids = Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
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
    dependencies = [("rbac", "0157_add_gst_report_export_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
