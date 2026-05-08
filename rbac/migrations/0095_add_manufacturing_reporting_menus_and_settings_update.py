from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "manufacturing_reporting_rbac_2026_05_07"
SEED_TAG = "manufacturing_reporting_rbac_seed"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


PERMISSION_SPECS = [
    (
        "manufacturing.settings.update",
        "manufacturing",
        "settings",
        "update",
        "Update Manufacturing Settings",
        "Save manufacturing settings and accounting controls.",
    ),
]


MENU_SPECS = [
    {
        "code": "reports.inventory.manufacturing_hub",
        "name": "Manufacturing Hub",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing",
        "route_name": "reports-manufacturing",
        "icon": "factory",
        "sort_order": 7,
        "permission_code": "manufacturing.workorder.view",
    },
    {
        "code": "reports.inventory.manufacturing_summary",
        "name": "Manufacturing Summary",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing/summary",
        "route_name": "reports-manufacturing-summary",
        "icon": "chart-donut",
        "sort_order": 8,
        "permission_code": "manufacturing.workorder.view",
    },
    {
        "code": "reports.inventory.manufacturing_material_consumption",
        "name": "Material Consumption Report",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing/material-consumption",
        "route_name": "reports-manufacturing-material-consumption",
        "icon": "package",
        "sort_order": 9,
        "permission_code": "manufacturing.workorder.view",
    },
    {
        "code": "reports.inventory.manufacturing_output_yield",
        "name": "Output And Yield Report",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing/output-yield",
        "route_name": "reports-manufacturing-output-yield",
        "icon": "chart-bar",
        "sort_order": 10,
        "permission_code": "manufacturing.workorder.view",
    },
    {
        "code": "reports.inventory.manufacturing_posting_audit",
        "name": "Posting Audit Report",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing/posting-audit",
        "route_name": "reports-manufacturing-posting-audit",
        "icon": "file-search",
        "sort_order": 11,
        "permission_code": "manufacturing.workorder.view",
    },
    {
        "code": "reports.inventory.manufacturing_wip_cost_summary",
        "name": "WIP And Cost Summary",
        "parent_code": "reports.inventory",
        "route_path": "/reports/manufacturing/wip-cost-summary",
        "route_name": "reports-manufacturing-wip-cost-summary",
        "icon": "coins",
        "sort_order": 12,
        "permission_code": "manufacturing.workorder.view",
    },
]


def _upsert_permission(Permission, code: str, module: str, resource: str, action: str, name: str, description: str):
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "module": module,
            "resource": resource,
            "action": action,
            "description": description,
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

    permission_by_code = {}
    for code, module, resource, action, name, description in PERMISSION_SPECS:
        permission_by_code[code] = _upsert_permission(
            Permission,
            code,
            module,
            resource,
            action,
            name,
            description,
        )

    permission_codes_needed = {spec["permission_code"] for spec in MENU_SPECS}
    permission_by_code.update(
        {
            permission.code: permission
            for permission in Permission.objects.filter(code__in=permission_codes_needed, isactive=True)
        }
    )

    for spec in MENU_SPECS:
        parent_menu = Menu.objects.filter(code=spec["parent_code"], isactive=True).first()
        if parent_menu is None:
            continue

        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent_menu.id,
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
                    "menu_code": spec["code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission = permission_by_code.get(spec["permission_code"])
        if permission is None:
            continue
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    admin_permissions = [
        permission.id
        for permission in permission_by_code.values()
        if permission.code == "manufacturing.settings.update"
    ]
    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=admin_permissions)
        .values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in admin_permissions:
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
    menu_ids = list(Menu.objects.filter(code__in=[spec["code"] for spec in MENU_SPECS]).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        MenuPermission.objects.filter(menu_id__in=menu_ids, relation_type=MENU_RELATION_VISIBILITY).delete()
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0094_grant_static_account_settings_admin_access"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
