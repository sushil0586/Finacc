from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
MENU_RELATION_ACTION = "action"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "asset_menu_path_reconcile_live_2026_05_10"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


CANONICAL_MENU_SPECS = (
    {
        "code": "assets.registry.asset-category-master",
        "name": "Asset Category Master",
        "parent_code": "assets.registry",
        "route_path": "asset-category-master",
        "route_name": "asset-category-master",
        "sort_order": 2,
        "is_system_menu": False,
        "permission_specs": (
            ("assets.category.view", "View Asset Category Master", "assets", "category", "view", MENU_RELATION_VISIBILITY),
            ("assets.category.create", "Create Asset Category Master", "assets", "category", "create", MENU_RELATION_ACTION),
            ("assets.category.update", "Update Asset Category Master", "assets", "category", "update", MENU_RELATION_ACTION),
            ("assets.category.delete", "Delete Asset Category Master", "assets", "category", "delete", MENU_RELATION_ACTION),
        ),
        "aliases": ("assetcategorymaster",),
    },
    {
        "code": "assets.registry.asset-master",
        "name": "Asset Master",
        "parent_code": "assets.registry",
        "route_path": "asset-master",
        "route_name": "asset-master",
        "sort_order": 1,
        "is_system_menu": False,
        "permission_specs": (
            ("assets.asset.view", "View Asset Master", "assets", "asset", "view", MENU_RELATION_VISIBILITY),
            ("assets.asset.create", "Create Asset Master", "assets", "asset", "create", MENU_RELATION_ACTION),
            ("assets.asset.update", "Update Asset Master", "assets", "asset", "update", MENU_RELATION_ACTION),
            ("assets.asset.delete", "Delete Asset Master", "assets", "asset", "delete", MENU_RELATION_ACTION),
        ),
        "aliases": ("assetmaster",),
    },
    {
        "code": "assets.depreciation.depreciation-run",
        "name": "Depreciation Run",
        "parent_code": "assets.depreciation",
        "route_path": "depreciation-run",
        "route_name": "depreciation-run",
        "sort_order": 1,
        "is_system_menu": False,
        "permission_specs": (
            ("assets.depreciation_run.view", "View Depreciation Run", "assets", "depreciation_run", "view", MENU_RELATION_VISIBILITY),
            ("assets.depreciation_run.create", "Create Depreciation Run", "assets", "depreciation_run", "create", MENU_RELATION_ACTION),
        ),
        "aliases": ("depreciationrun",),
    },
    {
        "code": "assets.controls.asset-settings",
        "name": "Asset Settings",
        "parent_code": "assets.controls",
        "route_path": "asset-settings",
        "route_name": "asset-settings",
        "sort_order": 2,
        "is_system_menu": False,
        "permission_specs": (
            ("assets.settings.view", "View Asset Settings", "assets", "settings", "view", MENU_RELATION_VISIBILITY),
            ("assets.settings.update", "Update Asset Settings", "assets", "settings", "update", MENU_RELATION_ACTION),
        ),
        "aliases": ("assetsettings",),
    },
    {
        "code": "reports.fixedassetregister",
        "name": "Fixed Asset Register",
        "parent_code": "reports",
        "route_path": "fixed-asset-register",
        "route_name": "fixed-asset-register",
        "sort_order": 30,
        "is_system_menu": True,
        "permission_specs": (
            ("assets.fixed_asset_register.view", "View Fixed Asset Register", "assets", "fixed_asset_register", "view", MENU_RELATION_VISIBILITY),
            ("assets.fixed_asset_register.export", "Export Fixed Asset Register", "assets", "fixed_asset_register", "export", MENU_RELATION_ACTION),
        ),
        "aliases": ("fixedassetregister",),
    },
    {
        "code": "reports.depreciationschedule",
        "name": "Depreciation Schedule",
        "parent_code": "reports",
        "route_path": "depreciation-schedule",
        "route_name": "depreciation-schedule",
        "sort_order": 31,
        "is_system_menu": True,
        "permission_specs": (
            ("assets.depreciation_schedule.view", "View Depreciation Schedule", "assets", "depreciation_schedule", "view", MENU_RELATION_VISIBILITY),
            ("assets.depreciation_schedule.export", "Export Depreciation Schedule", "assets", "depreciation_schedule", "export", MENU_RELATION_ACTION),
        ),
        "aliases": ("depreciationschedule",),
    },
    {
        "code": "reports.assetevents",
        "name": "Asset Events",
        "parent_code": "reports",
        "route_path": "asset-events",
        "route_name": "asset-events",
        "sort_order": 32,
        "is_system_menu": True,
        "permission_specs": (
            ("assets.asset_events.view", "View Asset Events", "assets", "asset_events", "view", MENU_RELATION_VISIBILITY),
            ("assets.asset_events.export", "Export Asset Events", "assets", "asset_events", "export", MENU_RELATION_ACTION),
        ),
        "aliases": ("assetevents",),
    },
    {
        "code": "reports.assethistory",
        "name": "Asset History",
        "parent_code": "reports",
        "route_path": "asset-history",
        "route_name": "asset-history",
        "sort_order": 33,
        "is_system_menu": True,
        "permission_specs": (
            ("assets.asset_history.view", "View Asset History", "assets", "asset_history", "view", MENU_RELATION_VISIBILITY),
            ("assets.asset_history.export", "Export Asset History", "assets", "asset_history", "export", MENU_RELATION_ACTION),
        ),
        "aliases": ("assethistory",),
    },
)


LEGACY_MENU_CODES_TO_DISABLE = (
    "assets.assetcategorymaster",
    "assets.assetmaster",
    "assets.depreciationrun",
    "assets.assetsettings",
    "assets.registry.fixed-asset-register",
    "assets.registry.asset-history",
    "assets.depreciation.depreciation-schedule",
    "assets.controls.asset-events",
)


def _merge_metadata(existing, extra):
    merged = dict(existing or {})
    merged.update(extra or {})
    return merged


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = set()

    for spec in CANONICAL_MENU_SPECS:
        parent = Menu.objects.filter(code=spec["parent_code"]).first()
        defaults = {
            "parent_id": parent.id if parent else None,
            "name": spec["name"],
            "menu_type": "screen",
            "route_path": spec["route_path"],
            "route_name": spec["route_name"],
            "sort_order": spec["sort_order"],
            "is_system_menu": spec["is_system_menu"],
            "metadata": {
                "seed": SEED_TAG,
                "aliases": list(spec.get("aliases", ())),
                "canonical_route": spec["route_path"],
            },
            "isactive": True,
        }
        menu, _ = Menu.objects.update_or_create(code=spec["code"], defaults=defaults)
        changed = False
        if not menu.isactive:
            menu.isactive = True
            changed = True
        merged_metadata = _merge_metadata(
            menu.metadata,
            {
                "seed": SEED_TAG,
                "aliases": list(spec.get("aliases", ())),
                "canonical_route": spec["route_path"],
            },
        )
        if menu.metadata != merged_metadata:
            menu.metadata = merged_metadata
            changed = True
        if changed:
            menu.save(update_fields=["isactive", "metadata", "updated_at"])

        for code, name, module, resource, action, relation_type in spec["permission_specs"]:
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
                    "metadata": {"seed": SEED_TAG, "menu_code": spec["code"]},
                    "isactive": True,
                },
            )
            if not permission.isactive:
                permission.isactive = True
                permission.save(update_fields=["isactive", "updated_at"])
            permission_ids.add(permission.id)
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission.id,
                relation_type=relation_type,
                defaults={"isactive": True},
            )

    if LEGACY_MENU_CODES_TO_DISABLE:
        Menu.objects.filter(code__in=LEGACY_MENU_CODES_TO_DISABLE).update(
            isactive=False,
            metadata=_merge_metadata({}, {"seed": SEED_TAG, "deactivated_as_duplicate": True}),
        )

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    if role_ids and permission_ids:
        existing = {
            (row.role_id, row.permission_id): row
            for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=list(permission_ids))
        }
        inserts = []
        for role_id in role_ids:
            for permission_id in permission_ids:
                row = existing.get((role_id, permission_id))
                if row is None:
                    inserts.append(
                        RolePermission(
                            role_id=role_id,
                            permission_id=permission_id,
                            effect=ROLE_PERMISSION_ALLOW,
                            metadata={"seed": SEED_TAG},
                            isactive=True,
                        )
                    )
                    continue
                changed = False
                if row.effect != ROLE_PERMISSION_ALLOW:
                    row.effect = ROLE_PERMISSION_ALLOW
                    changed = True
                if not row.isactive:
                    row.isactive = True
                    changed = True
                merged_metadata = _merge_metadata(row.metadata, {"seed": SEED_TAG})
                if row.metadata != merged_metadata:
                    row.metadata = merged_metadata
                    changed = True
                if changed:
                    row.save(update_fields=["effect", "isactive", "metadata", "updated_at"])
        if inserts:
            RolePermission.objects.bulk_create(inserts, batch_size=200)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0106_add_gst_exception_dashboard_report_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
