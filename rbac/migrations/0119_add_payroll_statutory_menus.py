from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "payroll_statutory_menus"
CATALOG_VERSION = "payroll_statutory_menus_2026_05_17"
ADMIN_ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
)


SCREEN_SPECS = (
    {
        "menu_code": "payroll.statutory-schemes",
        "name": "Statutory Schemes",
        "route_path": "/payroll/statutory/schemes",
        "route_name": "payroll-statutory-schemes",
        "icon": "shield-ellipsis",
        "sort_order": 5,
        "permission_codes": (
            "payroll.statutory_schemes.view",
            "payroll.statutory_schemes.create",
            "payroll.statutory_schemes.update",
            "payroll.statutory_schemes.delete",
        ),
    },
    {
        "menu_code": "payroll.statutory-rules",
        "name": "Statutory Rules",
        "route_path": "/payroll/statutory/rules",
        "route_name": "payroll-statutory-rules",
        "icon": "scale",
        "sort_order": 6,
        "permission_codes": (
            "payroll.statutory_rules.view",
            "payroll.statutory_rules.create",
            "payroll.statutory_rules.update",
            "payroll.statutory_rules.delete",
        ),
    },
    {
        "menu_code": "payroll.statutory-registrations",
        "name": "Statutory Registrations",
        "route_path": "/payroll/statutory/registrations",
        "route_name": "payroll-statutory-registrations",
        "icon": "file-check-2",
        "sort_order": 7,
        "permission_codes": (
            "payroll.statutory_registrations.view",
            "payroll.statutory_registrations.create",
            "payroll.statutory_registrations.update",
            "payroll.statutory_registrations.delete",
        ),
    },
    {
        "menu_code": "payroll.contract-statutory-profiles",
        "name": "Contract Statutory Profiles",
        "route_path": "/payroll/statutory/contract-profiles",
        "route_name": "payroll-contract-statutory-profiles",
        "icon": "shield-check",
        "sort_order": 8,
        "permission_codes": (
            "payroll.contract_statutory_profiles.view",
            "payroll.contract_statutory_profiles.create",
            "payroll.contract_statutory_profiles.update",
            "payroll.contract_statutory_profiles.delete",
        ),
    },
)


def _permission_name(code: str) -> str:
    labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1]).title()
    return f"{labels.get(action, action.title())} {resource}".strip()


def _permission_parts(code: str) -> tuple[str, str, str]:
    parts = code.split(".")
    return parts[0], ".".join(parts[1:-1]).replace(".", "_"), parts[-1]


def _upsert_permission(Permission, permission_code: str, *, menu_code: str) -> int:
    module, resource, action = _permission_parts(permission_code)
    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": _permission_name(permission_code),
            "module": module,
            "resource": resource,
            "action": action,
            "description": _permission_name(permission_code),
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": menu_code,
            },
            "isactive": True,
        },
    )
    return permission.id


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    root_menu = Menu.objects.get(code="payroll")
    roles = {role.code: role.id for role in Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True)}

    for spec in SCREEN_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["menu_code"],
            defaults={
                "parent_id": root_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "route_path": spec["route_path"],
                    "feature": "feature_payroll",
                    "access_mode": "setup",
                    "menu_group": "payroll",
                },
                "isactive": True,
            },
        )

        permission_ids = []
        for permission_code in spec["permission_codes"]:
            permission_ids.append(_upsert_permission(Permission, permission_code, menu_code=spec["menu_code"]))

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_ids[0],
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        existing_pairs = set(
            RolePermission.objects.filter(role_id__in=roles.values(), permission_id__in=permission_ids).values_list("role_id", "permission_id")
        )
        inserts = []
        for role_id in roles.values():
            for permission_id in permission_ids:
                if (role_id, permission_id) in existing_pairs:
                    continue
                inserts.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                        isactive=True,
                    )
                )
        if inserts:
            RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [code for spec in SCREEN_SPECS for code in spec["permission_codes"]]
    menu_codes = [spec["menu_code"] for spec in SCREEN_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0118_add_payroll_pay_item_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
