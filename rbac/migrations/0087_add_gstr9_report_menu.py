from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "gstr9_report_menu_2026_04_27"
SEED_NAME = "gstr9_report_menu"

PARENT_CANDIDATES = ["reports.compliance", "reports"]
MENU_CODE = "reports.gstr9report"

VIEW_PERMISSION_CODE = "reports.gstr9.view"
EXPORT_PERMISSION_CODE = "reports.gstr9.export"


ROLE_GRANT_SEEDS = [
    {
        "source_permission": "reports.gstr3b.view",
        "target_permission": VIEW_PERMISSION_CODE,
    },
    {
        "source_permission": "reports.gstr3b.export",
        "target_permission": EXPORT_PERMISSION_CODE,
    },
]


def _permission_parts(code: str):
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


def _upsert_permission(Permission, permission_code: str, *, description: str):
    module, resource, action = _permission_parts(permission_code)
    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": _permission_name(permission_code),
            "module": module,
            "resource": resource,
            "action": action,
            "description": description,
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_CODE,
            },
            "isactive": True,
        },
    )
    return permission


def _grant_permission_to_roles(RolePermission, *, role_ids, permission_id, metadata):
    for role_id in role_ids:
        RolePermission.objects.update_or_create(
            role_id=role_id,
            permission_id=permission_id,
            defaults={
                "effect": ROLE_PERMISSION_ALLOW,
                "metadata": metadata,
                "isactive": True,
            },
        )


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = None
    for code in PARENT_CANDIDATES:
        parent = Menu.objects.filter(code=code, isactive=True).first()
        if parent:
            break

    menu, _ = Menu.objects.update_or_create(
        code=MENU_CODE,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "GSTR-9 Annual Return",
            "menu_type": "screen",
            "route_path": "gstr9report",
            "route_name": "gstr9report",
            "icon": "file-earmark-text",
            "sort_order": 6,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "module": "reports",
                "report_code": "gstr9",
            },
            "isactive": True,
        },
    )

    view_permission = _upsert_permission(
        Permission,
        VIEW_PERMISSION_CODE,
        description="Access GSTR-9 annual return report.",
    )
    export_permission = _upsert_permission(
        Permission,
        EXPORT_PERMISSION_CODE,
        description="Export GSTR-9 annual return report.",
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=view_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )
    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=export_permission.id,
        relation_type=MENU_RELATION_ACTION,
        defaults={"isactive": True},
    )

    base_admin_role_ids = set(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )

    _grant_permission_to_roles(
        RolePermission,
        role_ids=base_admin_role_ids,
        permission_id=view_permission.id,
        metadata={"seed": SEED_NAME, "catalog_version": CATALOG_VERSION, "grant": "bootstrap"},
    )
    _grant_permission_to_roles(
        RolePermission,
        role_ids=base_admin_role_ids,
        permission_id=export_permission.id,
        metadata={"seed": SEED_NAME, "catalog_version": CATALOG_VERSION, "grant": "bootstrap"},
    )

    for grant in ROLE_GRANT_SEEDS:
        source_role_ids = set(
            RolePermission.objects.filter(
                permission__code=grant["source_permission"],
                role__isactive=True,
                isactive=True,
            ).values_list("role_id", flat=True)
        )
        if not source_role_ids:
            continue

        target_permission_id = view_permission.id if grant["target_permission"] == VIEW_PERMISSION_CODE else export_permission.id
        _grant_permission_to_roles(
            RolePermission,
            role_ids=source_role_ids,
            permission_id=target_permission_id,
            metadata={
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "grant": f"from_{grant['source_permission']}",
            },
        )


def backwards(apps, schema_editor):
    # Keep this forward-only to avoid accidental revocation in live tenants.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0086_add_sales_bulk_print_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
