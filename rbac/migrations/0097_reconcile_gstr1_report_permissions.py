from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "gstr1_report_permission_reconcile_2026_05_08"
SEED_NAME = "gstr1_report_permission_reconcile"
PARENT_CANDIDATES = ["reports.compliance", "reports"]

CANONICAL_MENU_CODE = "reports.gstr1report"
LEGACY_MENU_CODE = "reports.gstreport"

VIEW_PERMISSION_CODE = "reports.gstr1report.view"
EXPORT_PERMISSION_CODE = "reports.gstr1report.export"

LEGACY_VIEW_PERMISSION_CODE = "reports.gst.view"
LEGACY_EXPORT_PERMISSION_CODE = "reports.gst.export"

ROLE_GRANT_SEEDS = [
    {
        "source_permission": LEGACY_VIEW_PERMISSION_CODE,
        "target_permission": VIEW_PERMISSION_CODE,
    },
    {
        "source_permission": LEGACY_EXPORT_PERMISSION_CODE,
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
                "menu_code": CANONICAL_MENU_CODE,
                "canonical_for_route": "gstreport",
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

    canonical_menu, _ = Menu.objects.update_or_create(
        code=CANONICAL_MENU_CODE,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "GSTR-1 Outward",
            "menu_type": "screen",
            "route_path": "gstreport",
            "route_name": "gstreport",
            "icon": "file-spreadsheet",
            "sort_order": 1,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "module": "reports",
                "report_code": "gstr1",
                "canonical_permission": VIEW_PERMISSION_CODE,
                "canonical_export_permission": EXPORT_PERMISSION_CODE,
                "route_aliases": ["gstreport"],
            },
            "isactive": True,
        },
    )

    legacy_menu = Menu.objects.filter(code=LEGACY_MENU_CODE).first()
    if legacy_menu:
        metadata = dict(legacy_menu.metadata or {})
        metadata.update(
            {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "replaced_by": CANONICAL_MENU_CODE,
                "replacement_permission": VIEW_PERMISSION_CODE,
            }
        )
        legacy_menu.metadata = metadata
        legacy_menu.isactive = False
        legacy_menu.save(update_fields=["metadata", "isactive"])

    view_permission = _upsert_permission(
        Permission,
        VIEW_PERMISSION_CODE,
        description="Access GSTR-1 outward sales return report.",
    )
    export_permission = _upsert_permission(
        Permission,
        EXPORT_PERMISSION_CODE,
        description="Export GSTR-1 outward sales return report.",
    )

    if canonical_menu:
        MenuPermission.objects.update_or_create(
            menu_id=canonical_menu.id,
            permission_id=view_permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )
        MenuPermission.objects.update_or_create(
            menu_id=canonical_menu.id,
            permission_id=export_permission.id,
            relation_type=MENU_RELATION_ACTION,
            defaults={"isactive": True},
        )

    base_admin_role_ids = set(
        Role.objects.filter(code__in=["entity.super_admin", "admin", "entity.admin"], isactive=True).values_list("id", flat=True)
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
    # Keep this forward-only to avoid accidental permission/menu regression in live tenants.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0096_reconcile_asset_route_permissions_admin_access"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
