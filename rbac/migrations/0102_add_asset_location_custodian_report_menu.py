from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

MENU_SPEC = {
    "code": "reports.asset-location-custodian",
    "name": "Asset Location / Custodian",
    "menu_type": "screen",
    "route_path": "asset-location-custodian",
    "route_name": "asset-location-custodian",
    "sort_order": 5,
    "parent_code": "reports.assets",
    "icon": "map-pin",
}

PERMISSION_SPECS = (
    ("assets.asset_location_custodian.view", "View Asset Location Custodian Report", "assets", "asset_location_custodian", "view", MENU_RELATION_VISIBILITY),
    ("assets.asset_location_custodian.export", "Export Asset Location Custodian Report", "assets", "asset_location_custodian", "export", MENU_RELATION_ACTION),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = Menu.objects.filter(code=MENU_SPEC["parent_code"]).first()
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
                "seed": "asset_location_custodian_report_menu",
                "canonical_section": "reports.assets",
                "feature": "feature_assets",
            },
            "isactive": True,
        },
    )
    if not menu.isactive:
        menu.isactive = True
        menu.save(update_fields=["isactive", "updated_at"])

    permission_ids = []
    for code, name, module, resource, action, relation_type in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "asset_location_custodian_report_menu",
                    "menu_code": MENU_SPEC["code"],
                },
                "isactive": True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive", "updated_at"])
        permission_ids.append(permission.id)
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=relation_type,
            defaults={"isactive": True},
        )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing = {
        (row.role_id, row.permission_id)
        for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
    }
    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    scope_entity_id=None,
                    scope_subentity_id=None,
                    constraints={},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts, batch_size=200)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")

    Menu.objects.filter(code=MENU_SPEC["code"]).update(isactive=False)
    Permission.objects.filter(code__in=[spec[0] for spec in PERMISSION_SPECS]).update(isactive=False)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0101_correct_report_menu_hierarchy_live"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
