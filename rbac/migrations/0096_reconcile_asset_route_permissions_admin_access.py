from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "asset_route_permissions_admin_reconcile_2026_05_08"
CATALOG_VERSION = "asset_route_catalog_reconcile_2026_05_08"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


ASSET_ROUTE_SPECS = (
    {
        "route": "assetcategorymaster",
        "group": "assets",
        "label": "Asset Category Master",
        "view_permission": "assets.category.view",
        "actions": ("assets.category.create", "assets.category.update", "assets.category.delete"),
        "sort_order": 1,
    },
    {
        "route": "assetmaster",
        "group": "assets",
        "label": "Asset Master",
        "view_permission": "assets.asset.view",
        "actions": ("assets.asset.create", "assets.asset.update", "assets.asset.delete"),
        "sort_order": 2,
    },
    {
        "route": "depreciationrun",
        "group": "assets",
        "label": "Depreciation Run",
        "view_permission": "assets.depreciation_run.view",
        "actions": ("assets.depreciation_run.create",),
        "sort_order": 3,
    },
    {
        "route": "assetsettings",
        "group": "assets",
        "label": "Asset Settings",
        "view_permission": "assets.settings.view",
        "actions": ("assets.settings.update",),
        "sort_order": 20,
    },
    {
        "route": "fixedassetregister",
        "group": "reports",
        "label": "Fixed Asset Register",
        "view_permission": "assets.fixed_asset_register.view",
        "actions": ("assets.fixed_asset_register.export",),
        "sort_order": 30,
    },
    {
        "route": "depreciationschedule",
        "group": "reports",
        "label": "Depreciation Schedule",
        "view_permission": "assets.depreciation_schedule.view",
        "actions": ("assets.depreciation_schedule.export",),
        "sort_order": 31,
    },
    {
        "route": "assetevents",
        "group": "reports",
        "label": "Asset Events",
        "view_permission": "assets.asset_events.view",
        "actions": ("assets.asset_events.export",),
        "sort_order": 32,
    },
    {
        "route": "assethistory",
        "group": "reports",
        "label": "Asset History",
        "view_permission": "assets.asset_history.view",
        "actions": ("assets.asset_history.export",),
        "sort_order": 33,
    },
)


GROUP_SPECS = (
    ("assets", "Assets", 60, "building"),
    ("reports", "Reports", 80, "bar-chart-3"),
)


def _permission_parts(code: str):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _permission_name(code: str):
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "export": "Export",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1]).title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _menu_code(spec):
    return f"{spec['group']}.{spec['route'].replace('/', '.').replace(':', '_')}"


def _ensure_group_menu(Menu, *, code: str, name: str, sort_order: int, icon: str):
    menu, _ = Menu.objects.update_or_create(
        code=code,
        defaults={
            "parent_id": None,
            "name": name,
            "menu_type": "group",
            "route_path": "",
            "route_name": code,
            "icon": icon,
            "sort_order": sort_order,
            "is_system_menu": True,
            "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION, "group": code},
            "isactive": True,
        },
    )
    if not menu.isactive:
        menu.isactive = True
        menu.save(update_fields=["isactive", "updated_at"])
    return menu


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    group_menus = {
        code: _ensure_group_menu(Menu, code=code, name=name, sort_order=sort_order, icon=icon)
        for code, name, sort_order, icon in GROUP_SPECS
    }

    permission_ids = set()
    for spec in ASSET_ROUTE_SPECS:
        parent = group_menus[spec["group"]]
        menu_code = _menu_code(spec)
        menu, _ = Menu.objects.update_or_create(
            code=menu_code,
            defaults={
                "parent_id": parent.id,
                "name": spec["label"],
                "menu_type": "screen",
                "route_path": spec["route"],
                "route_name": spec["route"].replace("/", "-").replace(":", ""),
                "icon": "",
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "route": spec["route"],
                    "menu_group": spec["group"],
                },
                "isactive": True,
            },
        )
        if not menu.isactive:
            menu.isactive = True
            menu.save(update_fields=["isactive", "updated_at"])

        permission_codes = [spec["view_permission"], *spec["actions"]]
        for permission_code in permission_codes:
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
                        "route": spec["route"],
                        "menu_code": menu_code,
                    },
                    "isactive": True,
                },
            )
            if not permission.isactive:
                permission.isactive = True
                permission.save(update_fields=["isactive", "updated_at"])
            permission_ids.add(permission.id)

            relation_type = MENU_RELATION_VISIBILITY if permission_code == spec["view_permission"] else MENU_RELATION_ACTION
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission.id,
                relation_type=relation_type,
                defaults={"isactive": True},
            )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids or not permission_ids:
        return

    existing_rows = {
        (row.role_id, row.permission_id): row
        for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=list(permission_ids))
    }

    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            row = existing_rows.get((role_id, permission_id))
            if row is None:
                inserts.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                        isactive=True,
                    )
                )
                continue

            metadata = row.metadata or {}
            changed = False
            if row.effect != ROLE_PERMISSION_ALLOW:
                row.effect = ROLE_PERMISSION_ALLOW
                changed = True
            if not row.isactive:
                row.isactive = True
                changed = True
            if metadata.get("seed") != SEED_TAG:
                metadata["seed"] = SEED_TAG
                metadata["catalog_version"] = CATALOG_VERSION
                row.metadata = metadata
                changed = True
            if changed:
                update_fields = ["effect", "isactive", "metadata"]
                if hasattr(row, "updated_at"):
                    update_fields.append("updated_at")
                row.save(update_fields=update_fields)

    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0095_add_manufacturing_reporting_menus_and_settings_update"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
