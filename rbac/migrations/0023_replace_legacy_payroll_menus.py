from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
PERMISSION_SCOPE_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
CATALOG_VERSION = "payroll_menu_refresh_2026_03_16"

PAYROLL_MENU_SPECS = [
    ("payroll", None, "Payroll", "group", "", "payroll", 85, "wallet-cards"),
    ("payroll.dashboard", "payroll", "Dashboard", "screen", "payroll/dashboard", "payroll-dashboard", 1, "layout-dashboard"),
    ("payroll.runs", "payroll", "Runs", "screen", "payroll/runs", "payroll-runs", 2, "play-circle"),
    ("payroll.components", "payroll", "Components", "screen", "payroll/components", "payroll-components", 3, "component"),
    ("payroll.salary-structures", "payroll", "Salary Structures", "screen", "payroll/salary-structures", "payroll-salary-structures", 4, "network"),
    ("payroll.employee-profiles", "payroll", "Employee Profiles", "screen", "payroll/employee-profiles", "payroll-employee-profiles", 5, "users-round"),
    ("payroll.periods", "payroll", "Periods", "screen", "payroll/periods", "payroll-periods", 6, "calendar-days"),
    ("payroll.adjustments", "payroll", "Adjustments", "screen", "payroll/adjustments", "payroll-adjustments", 7, "sliders-horizontal"),
    ("payroll.reports", "payroll", "Reports", "screen", "payroll/reports", "payroll-reports", 8, "bar-chart-3"),
    ("payroll.onboarding", "payroll", "Onboarding", "screen", "payroll/onboarding", "payroll-onboarding", 9, "briefcase-business"),
]

LEGACY_MENU_CODES = [
    "admin.payroll",
    "admin.salarycomponent",
    "admin.employee",
    "admin.employeesalary",
    "admin.payrollstructure",
    "admin.compensation",
    "admin.emicalculator",
]


def _module_from_code(code):
    return code.split(".", 1)[0]


def _resource_from_code(code):
    return code.split(".")[-1].replace("-", "_")


def _permission_tuple(code, name, menu_type):
    module = _module_from_code(code)
    resource = _resource_from_code(code)
    action = "view" if menu_type == "screen" else "access"
    name_prefix = "View" if menu_type == "screen" else "Access"
    return (f"{module}.{resource}.{action}", f"{name_prefix} {name}", module, resource, action)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_by_code = {}
    permission_ids = []

    for code, parent_code, name, menu_type, route_path, route_name, sort_order, icon in PAYROLL_MENU_SPECS:
        parent = menu_by_code.get(parent_code)
        if parent is None and parent_code:
            parent = Menu.objects.filter(code=parent_code).first()
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={
                "parent_id": parent.id if parent else None,
                "name": name,
                "menu_type": menu_type,
                "route_path": route_path,
                "route_name": route_name,
                "icon": icon,
                "sort_order": sort_order,
                "is_system_menu": True,
                "metadata": {
                    "seed": "payroll_menu_refresh",
                    "catalog_version": CATALOG_VERSION,
                    "managed_root": "payroll",
                },
                "isactive": True,
            },
        )
        menu_by_code[code] = menu

        permission_code, permission_name, module, resource, action = _permission_tuple(code, name, menu_type)
        permission, _ = Permission.objects.update_or_create(
            code=permission_code,
            defaults={
                "name": permission_name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": permission_name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "payroll_menu_refresh",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": code,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    legacy_permission_codes = [
        _permission_tuple(menu.code, menu.name, menu.menu_type)[0]
        for menu in Menu.objects.filter(code__in=LEGACY_MENU_CODES)
    ]
    if legacy_permission_codes:
        Permission.objects.filter(code__in=legacy_permission_codes).update(isactive=False)
    Menu.objects.filter(code__in=LEGACY_MENU_CODES).update(isactive=False)

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    existing = set(RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id"))
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) not in existing:
                rows.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": "payroll_menu_refresh", "catalog_version": CATALOG_VERSION},
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

    payroll_codes = [spec[0] for spec in PAYROLL_MENU_SPECS]
    permission_codes = [_permission_tuple(code, name, menu_type)[0] for code, _, name, menu_type, *_ in PAYROLL_MENU_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    Menu.objects.filter(code__in=payroll_codes).delete()
    Menu.objects.filter(code__in=LEGACY_MENU_CODES).update(isactive=True)
    Permission.objects.filter(code__in=[
        "admin.payroll.access",
        "admin.salarycomponent.view",
        "admin.employee.view",
        "admin.employeesalary.view",
        "admin.payrollstructure.view",
        "admin.compensation.view",
        "admin.emicalculator.view",
    ]).update(isactive=True)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0022_add_payables_reporting_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
