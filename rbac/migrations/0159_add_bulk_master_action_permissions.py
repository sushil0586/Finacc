from django.db import migrations


SEED_TAG = "bulk_master_action_permissions_2026_09_13"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
PERMISSIONS = (
    ("financial.account.export", "Export Accounts", "financial", "account", "export", "financialmaster/accounts"),
    ("financial.account.import", "Import Accounts", "financial", "account", "import", "financialmaster/accounts"),
    ("catalog.product.export", "Export Products", "catalog", "product", "export", "catalogproducts"),
    ("catalog.product.import", "Import Products", "catalog", "product", "import", "catalogproducts"),
    ("catalog.hsn_sac.export", "Export HSN SAC", "catalog", "hsn_sac", "export", "cataloghsnsac"),
    ("catalog.hsn_sac.import", "Import HSN SAC", "catalog", "hsn_sac", "import", "cataloghsnsac"),
    ("compliance.tcs_section.export", "Export TCS Sections", "compliance", "tcs_section", "export", "tcssections"),
    ("compliance.tcs_section.import", "Import TCS Sections", "compliance", "tcs_section", "import", "tcssections"),
    ("compliance.tcs_rule.export", "Export TCS Rules", "compliance", "tcs_rule", "export", "tcsrules"),
    ("compliance.tcs_rule.import", "Import TCS Rules", "compliance", "tcs_rule", "import", "tcsrules"),
    ("compliance.tcs_config.export", "Export TCS Config", "compliance", "tcs_config", "export", "tcsconfig"),
    ("compliance.tcs_config.import", "Import TCS Config", "compliance", "tcs_config", "import", "tcsconfig"),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    for code, name, module, resource, action, route_path in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
        for menu in Menu.objects.filter(route_path=route_path, isactive=True):
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
    dependencies = [("rbac", "0158_add_purchase_statutory_export_permission")]
    operations = [migrations.RunPython(forwards, backwards)]
