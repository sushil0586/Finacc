from django.db import migrations


SEED_TAG = "inventory_report_export_permission_2026_09_13"
PERMISSION_CODE = "reports.inventory.export"
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
            "name": "Export Inventory Reports",
            "module": "reports",
            "resource": "inventory",
            "action": "export",
            "description": "Export or print inventory reports.",
            "scope_type": "entity",
            "is_system_defined": True,
            "metadata": {"seed": SEED_TAG},
            "isactive": True,
        },
    )

    menu = Menu.objects.filter(code="reports.inventory", isactive=True).first()
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
    # Keep the live authorization catalog intact on code rollback.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0153_sync_purchase_document_menu_actions")]
    operations = [migrations.RunPython(forwards, backwards)]
