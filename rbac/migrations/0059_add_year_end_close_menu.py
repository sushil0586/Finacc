from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "year_end_close_menu_2026_04_14"


MENU_SPEC = {
    "code": "reports.financial_hub.year_end_close",
    "name": "Year-End Close",
    "parent_code": "reports.financial_hub",
    "route_path": "/reports/controls/year-end-close",
    "route_name": "controls-year-end-close",
    "icon": "shield-check",
    "sort_order": 10,
    "permission_code": "reports.financial_hub.year_end_close.view",
}


def _permission_parts(code: str) -> tuple[str, str, str]:
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "print": "Print",
        "post": "Post",
        "unpost": "Unpost",
        "export": "Export",
        "file": "File",
        "change": "Change",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1])
    resource = resource.title() if resource else parts[0].title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _upsert_permission(Permission, permission_code: str, *, seed: str, menu_code: str) -> int:
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
                "seed": seed,
                "catalog_version": CATALOG_VERSION,
                "menu_code": menu_code,
            },
            "isactive": True,
        },
    )
    return permission.id


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
                "seed": "year_end_close_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["code"],
                "route_path": MENU_SPEC["route_path"],
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission_id = _upsert_permission(
        Permission,
        MENU_SPEC["permission_code"],
        seed="year_end_close_menu",
        menu_code=MENU_SPEC["code"],
    )
    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission_id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    source_role_ids = set(
        RolePermission.objects.filter(
            permission__code="reports.financial_hub.view",
            role__isactive=True,
        ).values_list("role_id", flat=True)
    )
    if not source_role_ids:
        source_role_ids.update(
            Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True)
        )

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=source_role_ids,
            permission_id=permission_id,
        ).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in source_role_ids:
        if (role_id, permission_id) in existing_pairs:
            continue
        inserts.append(
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": "year_end_close_menu", "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
        )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0058_add_controls_phase_one_menu")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
