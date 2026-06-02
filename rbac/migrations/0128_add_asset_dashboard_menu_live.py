from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

MENU_SPEC = {
    "code": "assets.registry.asset-dashboard",
    "name": "Asset Dashboard",
    "menu_type": "screen",
    "route_path": "asset-dashboard",
    "route_name": "asset-dashboard",
    "sort_order": 0,
    "parent_code": "assets.registry",
    "icon": "speedometer2",
}

PERMISSION_CODE = "assets.asset_dashboard.view"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code=MENU_SPEC["parent_code"], isactive=True).first()
    if parent is None:
        parent = Menu.objects.filter(code="assets", isactive=True).first()
    if parent is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": parent.id,
            "name": MENU_SPEC["name"],
            "menu_type": MENU_SPEC["menu_type"],
            "route_path": MENU_SPEC["route_path"],
            "route_name": MENU_SPEC["route_name"],
            "icon": MENU_SPEC["icon"],
            "sort_order": MENU_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "asset_dashboard_menu_live",
                "canonical_section": "assets",
                "feature": "feature_assets",
            },
            "isactive": True,
        },
    )
    if not menu.isactive:
        menu.isactive = True
        menu.save(update_fields=["isactive", "updated_at"])

    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "View Asset Dashboard",
            "module": "assets",
            "resource": "asset_dashboard",
            "action": "view",
            "description": "View Asset Dashboard",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": "asset_dashboard_menu_live",
                "menu_code": MENU_SPEC["code"],
            },
            "isactive": True,
        },
    )
    if not permission.isactive:
        permission.isactive = True
        permission.save(update_fields=["isactive", "updated_at"])

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type="visibility",
        defaults={"isactive": True},
    )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing = {
        row.role_id
        for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id, effect=ROLE_PERMISSION_ALLOW)
    }
    inserts = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            isactive=True,
        )
        for role_id in role_ids
        if role_id not in existing
    ]
    if inserts:
        RolePermission.objects.bulk_create(inserts, batch_size=200)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")

    Menu.objects.filter(code=MENU_SPEC["code"]).update(isactive=False)
    Permission.objects.filter(code=PERMISSION_CODE).update(isactive=False)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0127_add_asset_location_custodian_report_menu_live"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
