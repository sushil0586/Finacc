from django.db import migrations


SEED_TAG = "sales_ar_permissions_2026_09_13"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSIONS = (
    ("sales.ar.view", "View Sales Receivables", "view"),
    ("sales.ar.manage", "Manage Sales Settlements", "manage"),
    ("sales.ar.export", "Export Sales Receivables", "export"),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    sales_menu = Menu.objects.filter(code="sales", isactive=True).first()

    for code, name, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "sales",
                "resource": "ar",
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
        if sales_menu:
            MenuPermission.objects.update_or_create(
                menu=sales_menu,
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
    dependencies = [("rbac", "0154_add_inventory_report_export_permission")]
    operations = [migrations.RunPython(forwards, backwards)]
