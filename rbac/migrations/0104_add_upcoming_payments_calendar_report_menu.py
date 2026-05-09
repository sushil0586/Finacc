from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "upcoming_payments_calendar_menu_2026_05_08"


REPORT_SPEC = {
    "menu_code": "reports.payables.upcoming_payments_calendar",
    "name": "Upcoming Payments Calendar",
    "route_path": "/reports/payables/upcoming_payments_calendar",
    "route_name": "reports-payables-upcoming-payments-calendar",
    "icon": "calendar-days",
    "sort_order": 26,
    "permission_code": "reports.payables.upcoming_payments_calendar.view",
}


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = (
        Menu.objects.filter(code="reports.payables", isactive=True).first()
        or Menu.objects.filter(code="reports.reports.payables", isactive=True).first()
    )
    if parent_menu is None:
        return

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin", "report_viewer"], isactive=True).values_list("id", flat=True)
    )

    menu, _ = Menu.objects.update_or_create(
        code=REPORT_SPEC["menu_code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": REPORT_SPEC["name"],
            "menu_type": "screen",
            "route_path": REPORT_SPEC["route_path"],
            "route_name": REPORT_SPEC["route_name"],
            "icon": REPORT_SPEC["icon"],
            "sort_order": REPORT_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "upcoming_payments_calendar_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": REPORT_SPEC["menu_code"],
                "permission_code": REPORT_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission, _ = Permission.objects.update_or_create(
        code=REPORT_SPEC["permission_code"],
        defaults={
            "name": "Reports Payables Upcoming Payments Calendar View",
            "module": "reports",
            "resource": "payables",
            "action": "view",
            "description": "Reports Payables Upcoming Payments Calendar View",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "upcoming_payments_calendar_menu",
                "catalog_version": CATALOG_VERSION,
                "menu_code": REPORT_SPEC["menu_code"],
            },
            "isactive": True,
        },
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", "permission_id")
    )
    rows = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            metadata={"seed": "upcoming_payments_calendar_menu", "catalog_version": CATALOG_VERSION},
            isactive=True,
        )
        for role_id in role_ids
        if (role_id, permission.id) not in existing_pairs
    ]
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code=REPORT_SPEC["permission_code"]).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code=REPORT_SPEC["menu_code"]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0103_add_inventory_slow_dead_stock_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
