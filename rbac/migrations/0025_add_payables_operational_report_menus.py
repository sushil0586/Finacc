from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
PERMISSION_SCOPE_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"


def _permission_tuple(code, name):
    module = code.split(".", 1)[0]
    resource = code.split(".")[-1].replace("-", "_")
    return (f"{module}.{resource}.view", f"View {name}", module, resource, "view")


def _seed_menu(apps, *, code, name, route_path, route_name, icon, sort_order):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code="reports.financial").first() or Menu.objects.filter(code="reports").first()
    menu, _ = Menu.objects.update_or_create(
        code=code,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": name,
            "menu_type": "screen",
            "route_path": route_path,
            "route_name": route_name,
            "icon": icon,
            "sort_order": sort_order,
            "is_system_menu": True,
            "metadata": {"seed": "payables_operational_reporting", "menu_code": code},
            "isactive": True,
        },
    )

    permission_code, permission_name, module, resource, action = _permission_tuple(code, name)
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
            "metadata": {"seed": "payables_operational_reporting", "menu_code": code},
            "isactive": True,
        },
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    existing = set(RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", flat=True))
    rows = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            metadata={"seed": "payables_operational_reporting"},
            isactive=True,
        )
        for role_id in role_ids
        if role_id not in existing
    ]
    if rows:
        RolePermission.objects.bulk_create(rows)


def forwards(apps, schema_editor):
    _seed_menu(apps, code="reports.vendorledgerstatement", name="Vendor Ledger Statement", route_path="vendorledgerstatement", route_name="vendorledgerstatement", icon="book-text", sort_order=18)
    _seed_menu(apps, code="reports.payablesclosepack", name="Payables Close Pack", route_path="payablesclosepack", route_name="payablesclosepack", icon="briefcase-business", sort_order=19)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code__in=["reports.vendorledgerstatement.view", "reports.payablesclosepack.view"]).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=["reports.vendorledgerstatement", "reports.payablesclosepack"]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0024_merge_payables_control_and_payroll")]

    operations = [migrations.RunPython(forwards, backwards)]
