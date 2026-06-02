from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "gst_reconciliation_workspace_2026_05_20"


WORKSPACE_MENU = {
    "menu_code": "compliance.gst_reconciliation",
    "name": "GST Reconciliation",
    "route_path": "gst-reconciliation",
    "route_name": "gst-reconciliation",
    "icon": "git-compare",
    "sort_order": 30,
    "permission_code": "gst.reconciliation.view",
}


EXTRA_PERMISSIONS = [
    {
        "code": "gst.reconciliation.review",
        "name": "GST Reconciliation Review",
        "module": "gst",
        "resource": "reconciliation",
        "action": "review",
        "description": "Review and resolve GST reconciliation items.",
    },
    {
        "code": "gst.reconciliation.manage",
        "name": "GST Reconciliation Manage",
        "module": "gst",
        "resource": "reconciliation",
        "action": "manage",
        "description": "Import, run matching, and close GST reconciliation runs.",
    },
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code="compliance", isactive=True).first()
    if parent_menu is None:
        return

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))

    menu, _ = Menu.objects.update_or_create(
        code=WORKSPACE_MENU["menu_code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": WORKSPACE_MENU["name"],
            "menu_type": "screen",
            "route_path": WORKSPACE_MENU["route_path"],
            "route_name": WORKSPACE_MENU["route_name"],
            "icon": WORKSPACE_MENU["icon"],
            "sort_order": WORKSPACE_MENU["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "gst_reconciliation_workspace_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": WORKSPACE_MENU["menu_code"],
            },
            "isactive": True,
        },
    )

    created_permissions = []
    view_permission, _ = Permission.objects.update_or_create(
        code=WORKSPACE_MENU["permission_code"],
        defaults={
            "name": "GST Reconciliation View",
            "module": "gst",
            "resource": "reconciliation",
            "action": "view",
            "description": "View GST reconciliation workspace.",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "gst_reconciliation_workspace_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": WORKSPACE_MENU["menu_code"],
            },
            "isactive": True,
        },
    )
    created_permissions.append(view_permission)

    for spec in EXTRA_PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "module": spec["module"],
                "resource": spec["resource"],
                "action": spec["action"],
                "description": spec["description"],
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "gst_reconciliation_workspace_menu",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": WORKSPACE_MENU["menu_code"],
                },
                "isactive": True,
            },
        )
        created_permissions.append(permission)

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=view_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=role_ids,
            permission_id__in=[permission.id for permission in created_permissions],
        ).values_list("role_id", "permission_id")
    )
    rows = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            metadata={"seed": "gst_reconciliation_workspace_menu", "catalog_version": CATALOG_VERSION},
            isactive=True,
        )
        for role_id in role_ids
        for permission in created_permissions
        if (role_id, permission.id) not in existing_pairs
    ]
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [WORKSPACE_MENU["permission_code"], *[spec["code"] for spec in EXTRA_PERMISSIONS]]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code=WORKSPACE_MENU["menu_code"]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0106_add_gst_exception_dashboard_report_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
