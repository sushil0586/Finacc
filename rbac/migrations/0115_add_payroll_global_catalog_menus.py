from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "payroll_global_catalog_menus"
CATALOG_VERSION = "payroll_global_catalog_menus_2026_05_17"
ADMIN_ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "payroll_operator",
    "payroll_read_only_reviewer",
)


SCREEN_SPECS = (
    {
        "menu_code": "payroll.global-component-groups",
        "name": "Global Component Groups",
        "route_path": "/payroll/global/component-groups",
        "route_name": "payroll-global-component-groups",
        "icon": "boxes",
        "sort_order": 10,
        "permission_codes": (
            "payroll.global_component_group.view",
            "payroll.global_component_group.manage",
            "payroll.global_component_group.create",
            "payroll.global_component_group.edit",
        ),
    },
    {
        "menu_code": "payroll.global-components",
        "name": "Global Components",
        "route_path": "/payroll/global/components",
        "route_name": "payroll-global-components",
        "icon": "package-plus",
        "sort_order": 11,
        "permission_codes": (
            "payroll.global_component.view",
            "payroll.global_component.manage",
            "payroll.global_component.create",
            "payroll.global_component.edit",
        ),
    },
    {
        "menu_code": "payroll.global-salary-templates",
        "name": "Global Salary Templates",
        "route_path": "/payroll/global/salary-templates",
        "route_name": "payroll-global-salary-templates",
        "icon": "files",
        "sort_order": 12,
        "permission_codes": (
            "payroll.global_salary_template.view",
            "payroll.global_salary_template.manage",
            "payroll.global_salary_template.create",
            "payroll.global_salary_template.edit",
            "payroll.global_salary_template.adopt",
        ),
    },
)


READ_ONLY_ROLE_CODE = "payroll_read_only_reviewer"
OPERATOR_ROLE_CODE = "payroll_operator"


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "manage": "Manage",
        "create": "Create",
        "edit": "Edit",
        "adopt": "Adopt",
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
            RolePermission.objects.filter(
                role_id__in=roles.values(),
                permission_id__in=permission_ids,
            ).values_list("role_id", "permission_id")
        )
        inserts = []
        for role_code, role_id in roles.items():
            for permission_code, permission_id in zip(spec["permission_codes"], permission_ids):
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

    permission_codes = []
    menu_codes = []
    for spec in SCREEN_SPECS:
        menu_codes.append(spec["menu_code"])
        permission_codes.extend(spec["permission_codes"])

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0114_add_hrms_setup_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
