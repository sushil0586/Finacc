from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "repair_account_bulk_master_permissions_2026_10_03"

ACCOUNT_BULK_PERMISSION_SPECS = (
    (
        "financial.account.export",
        "Export Accounts",
        "financial",
        "account",
        "export",
        "financialmaster/accounts",
    ),
    (
        "financial.account.import",
        "Import Accounts",
        "financial",
        "account",
        "import",
        "financialmaster/accounts",
    ),
)

TARGET_ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "accounts_manager",
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(
        Role.objects.filter(code__in=TARGET_ROLE_CODES, isactive=True)
        .values_list("id", flat=True)
    )

    for code, name, module, resource, action, route_path in ACCOUNT_BULK_PERMISSION_SPECS:
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
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )

        route_variants = {route_path, f"/{route_path}"}
        for menu in Menu.objects.filter(route_path__in=route_variants, isactive=True):
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
                    "effect": ROLE_PERMISSION_ALLOW,
                    "metadata": {"seed": SEED_TAG},
                    "isactive": True,
                },
            )


def backwards(apps, schema_editor):
    # Preserve repaired launch permissions on rollback; the permission catalog is
    # forward-owned by canonical RBAC seeding.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0215_retire_legacy_tds_report_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
