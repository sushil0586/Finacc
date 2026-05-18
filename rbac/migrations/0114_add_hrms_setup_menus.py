from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "hrms_setup_menus"
CATALOG_VERSION = "hrms_setup_menus_2026_05_17"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


MENU_GROUP = {
    "code": "hrms",
    "name": "HRMS",
    "route_path": "/hrms",
    "route_name": "hrms",
    "icon": "people",
    "sort_order": 41,
}


SCREEN_SPECS = (
    {
        "menu_code": "hrms.organization_units",
        "name": "Organization Units",
        "route_path": "/hrms/organization-units",
        "route_name": "hrms-organization-units",
        "icon": "diagram-3",
        "sort_order": 1,
        "permission_prefix": "hrms.organization_unit",
    },
    {
        "menu_code": "hrms.employees",
        "name": "Employees",
        "route_path": "/hrms/employees",
        "route_name": "hrms-employees",
        "icon": "person-vcard",
        "sort_order": 2,
        "permission_prefix": "hrms.employee",
    },
    {
        "menu_code": "hrms.contracts",
        "name": "Employment Contracts",
        "route_path": "/hrms/contracts",
        "route_name": "hrms-contracts",
        "icon": "file-earmark-text",
        "sort_order": 3,
        "permission_prefix": "hrms.employment_contract",
    },
    {
        "menu_code": "hrms.shifts",
        "name": "Shifts",
        "route_path": "/hrms/shifts",
        "route_name": "hrms-shifts",
        "icon": "clock-history",
        "sort_order": 4,
        "permission_prefix": "hrms.shift",
    },
    {
        "menu_code": "hrms.holiday_calendars",
        "name": "Holiday Calendars",
        "route_path": "/hrms/holiday-calendars",
        "route_name": "hrms-holiday-calendars",
        "icon": "calendar4-week",
        "sort_order": 5,
        "permission_prefix": "hrms.holiday_calendar",
    },
)


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
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

    root_menu, _ = Menu.objects.update_or_create(
        code=MENU_GROUP["code"],
        defaults={
            "name": MENU_GROUP["name"],
            "menu_type": "group",
            "route_path": MENU_GROUP["route_path"],
            "route_name": MENU_GROUP["route_name"],
            "icon": MENU_GROUP["icon"],
            "sort_order": MENU_GROUP["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "feature": "feature_payroll",
                "access_mode": "setup",
                "menu_group": "hrms",
            },
            "isactive": True,
        },
    )

    admin_role_ids = set(
        Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
    )

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
                    "menu_group": "hrms",
                },
                "isactive": True,
            },
        )

        permission_codes = [
            f"{spec['permission_prefix']}.view",
            f"{spec['permission_prefix']}.create",
            f"{spec['permission_prefix']}.update",
            f"{spec['permission_prefix']}.delete",
        ]
        permission_ids = []
        for permission_code in permission_codes:
            permission_ids.append(_upsert_permission(Permission, permission_code, menu_code=spec["menu_code"]))

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_ids[0],
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        existing_pairs = set(
            RolePermission.objects.filter(
                role_id__in=admin_role_ids,
                permission_id__in=permission_ids,
            ).values_list("role_id", "permission_id")
        )
        inserts = []
        for role_id in admin_role_ids:
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

    permission_codes = []
    menu_codes = [MENU_GROUP["code"]]
    for spec in SCREEN_SPECS:
        menu_codes.append(spec["menu_code"])
        permission_codes.extend(
            [
                f"{spec['permission_prefix']}.view",
                f"{spec['permission_prefix']}.create",
                f"{spec['permission_prefix']}.update",
                f"{spec['permission_prefix']}.delete",
            ]
        )

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0113_add_legacy_invoice_import_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
