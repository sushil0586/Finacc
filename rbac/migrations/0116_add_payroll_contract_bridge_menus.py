from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "payroll_contract_bridge_menus"
CATALOG_VERSION = "payroll_contract_bridge_menus_2026_05_17"
ADMIN_ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "payroll_operator",
    "payroll_read_only_reviewer",
)


SCREEN_SPEC = {
    "menu_code": "payroll.contract-profiles",
    "name": "Contract Payroll Profiles",
    "route_path": "/payroll/contract-profiles",
    "route_name": "payroll-contract-profiles",
    "icon": "file-user",
    "sort_order": 6,
    "permission_codes": (
        "payroll.contract_profile.view",
        "payroll.contract_profile.manage",
        "payroll.contract_profile.create",
        "payroll.contract_profile.edit",
        "payroll.contract_salary_assignment.view",
        "payroll.contract_salary_assignment.manage",
        "payroll.contract_salary_assignment.create",
        "payroll.contract_salary_assignment.edit",
    ),
}


READ_ONLY_ROLE_CODE = "payroll_read_only_reviewer"
OPERATOR_ROLE_CODE = "payroll_operator"


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "manage": "Manage",
        "create": "Create",
        "edit": "Edit",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1])
    resource = resource.title() if resource else parts[0].title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _permission_parts(code: str) -> tuple[str, str, str]:
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _role_allows_permission(role_code: str, permission_code: str) -> bool:
    if role_code in {"entity.super_admin", "admin", "entity.admin"}:
        return True
    if role_code == OPERATOR_ROLE_CODE:
        return True
    if role_code == READ_ONLY_ROLE_CODE:
        return permission_code.endswith(".view")
    return False


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
    roles = {
        role.code: role.id
        for role in Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True)
    }

    menu, _ = Menu.objects.update_or_create(
        code=SCREEN_SPEC["menu_code"],
        defaults={
            "parent_id": root_menu.id,
            "name": SCREEN_SPEC["name"],
            "menu_type": "screen",
            "route_path": SCREEN_SPEC["route_path"],
            "route_name": SCREEN_SPEC["route_name"],
            "icon": SCREEN_SPEC["icon"],
            "sort_order": SCREEN_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": SCREEN_SPEC["menu_code"],
                "route_path": SCREEN_SPEC["route_path"],
                "feature": "feature_payroll",
                "access_mode": "setup",
                "menu_group": "payroll",
            },
            "isactive": True,
        },
    )

    permission_ids = []
    for permission_code in SCREEN_SPEC["permission_codes"]:
        permission_ids.append(_upsert_permission(Permission, permission_code, menu_code=SCREEN_SPEC["menu_code"]))

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission_ids[0],
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=roles.values(),
            permission_id__in=permission_ids,
        ).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_code, role_id in roles.items():
        for permission_code, permission_id in zip(SCREEN_SPEC["permission_codes"], permission_ids):
            if not _role_allows_permission(role_code, permission_code):
                continue
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

    permission_codes = list(SCREEN_SPEC["permission_codes"])
    menu_codes = [SCREEN_SPEC["menu_code"]]

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0115_add_payroll_global_catalog_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
