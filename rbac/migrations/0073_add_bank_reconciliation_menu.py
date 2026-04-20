from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "bank_reconciliation_menu_2026_04_19"
SEED_TAG = "bank_reconciliation_menu_seed"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin", "report_viewer")


MENU_SPEC = {
    "code": "reports.financial_hub.bank_reconciliation",
    "name": "Bank Reconciliation",
    "parent_code": "reports.financial_hub",
    "route_path": "/reports/bank-reconciliation",
    "route_name": "bank-reconciliation",
    "icon": "scale",
    "sort_order": 11,
    "permission_code": "reports.financial_hub.bank_reconciliation.view",
}


PERMISSION_SPECS = [
    ("reports.financial_hub.bank_reconciliation.view", "reports", "financial_hub_bank_reconciliation", "view", "View Bank Reconciliation"),
    ("reports.financial_hub.bank_reconciliation.create", "reports", "financial_hub_bank_reconciliation", "create", "Create Bank Reconciliation"),
    ("reports.financial_hub.bank_reconciliation.update", "reports", "financial_hub_bank_reconciliation", "update", "Update Bank Reconciliation"),
    ("reports.financial_hub.bank_reconciliation.import", "reports", "financial_hub_bank_reconciliation", "import", "Import Bank Reconciliation"),
]


def _upsert_permission(Permission, code: str, module: str, resource: str, action: str, name: str):
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
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": code,
            },
            "isactive": True,
        },
    )
    return permission


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code=MENU_SPEC["parent_code"], isactive=True).first()
    if parent_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": MENU_SPEC["name"],
            "menu_type": "screen",
            "route_path": MENU_SPEC["route_path"],
            "route_name": MENU_SPEC["route_name"],
            "icon": MENU_SPEC["icon"],
            "sort_order": MENU_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["code"],
                "route_path": MENU_SPEC["route_path"],
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission_by_code = {
        code: _upsert_permission(Permission, code, module, resource, action, name)
        for code, module, resource, action, name in PERMISSION_SPECS
    }
    permission = permission_by_code[MENU_SPEC["permission_code"]]
    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    permission_ids = [item.id for item in permission_by_code.values()]
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [row[0] for row in PERMISSION_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    Menu.objects.filter(code=MENU_SPEC["code"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0072_add_retail_phase6_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
