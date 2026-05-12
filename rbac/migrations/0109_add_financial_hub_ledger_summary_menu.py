from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "financial_hub_ledger_summary_menu"
CATALOG_VERSION = "financial_hub_ledger_summary_menu_2026_05_12"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

MENU_SPEC = {
    "code": "reports.financial_hub.ledger_summary",
    "name": "Ledger Summary",
    "route_path": "/ledgersummary",
    "route_name": "ledgersummary",
    "icon": "book-a",
    "sort_order": 4,
    "permission_code": "reports.financial_hub.ledger_summary.view",
    "export_permission_code": "reports.financial_hub.ledger_summary.export",
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
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    group_menu = Menu.objects.filter(code="reports.financial_hub", isactive=True).first()
    if group_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": group_menu.id,
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

    permission_ids: list[int] = []
    for code_key in ("permission_code", "export_permission_code"):
        permission_code = MENU_SPEC.get(code_key)
        if not permission_code:
            continue
        permission_id = _upsert_permission(Permission, permission_code, menu_code=MENU_SPEC["code"])
        permission_ids.append(permission_id)
        if code_key == "permission_code":
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission_id,
                relation_type=MENU_RELATION_VISIBILITY,
                defaults={"isactive": True},
            )

    source_permission_codes = [
        "reports.financial_hub.view",
        "reports.financial_hub.ledger_book.view",
        "reports.ledger_book.view",
        "reports.ledgersummary.view",
    ]
    role_ids = set()
    for code in source_permission_codes:
        role_ids.update(
            RolePermission.objects.filter(
                permission__code=code,
                role__isactive=True,
            ).values_list("role_id", flat=True)
        )

    if not role_ids:
        role_ids.update(
            Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
        )

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
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(
        Permission.objects.filter(
            code__in=[MENU_SPEC["permission_code"], MENU_SPEC["export_permission_code"]]
        ).values_list("id", flat=True)
    )
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code=MENU_SPEC["code"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0108_add_financial_hub_settings_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
