from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
PERMISSION_SCOPE_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"


def _permission_tuple(code, name):
    module = code.split(".", 1)[0]
    resource = code.split(".")[-1].replace("-", "_")
    return (f"{module}.{resource}.view", f"View {name}", module, resource, "view")


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code="reports.financial").first() or Menu.objects.filter(code="reports").first()
    menu, _ = Menu.objects.update_or_create(
        code="reports.vendoroutstanding",
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "Vendor Outstanding",
            "menu_type": "screen",
            "route_path": "vendoroutstanding",
            "route_name": "vendoroutstanding",
            "icon": "wallet-minimal",
            "sort_order": 13 if parent and parent.code == "reports.financial" else 17,
            "is_system_menu": True,
            "metadata": {"seed": "payables_reporting", "menu_code": "reports.vendoroutstanding"},
            "isactive": True,
        },
    )

    permission_code, permission_name, module, resource, action = _permission_tuple("reports.vendoroutstanding", "Vendor Outstanding")
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
            "metadata": {"seed": "payables_reporting", "menu_code": "reports.vendoroutstanding"},
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
            metadata={"seed": "payables_reporting"},
            isactive=True,
        )
        for role_id in role_ids
        if role_id not in existing
    ]
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code="reports.vendoroutstanding.view").values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code="reports.vendoroutstanding").values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0021_restore_grouped_menu_hierarchy")]

    operations = [migrations.RunPython(forwards, backwards)]
