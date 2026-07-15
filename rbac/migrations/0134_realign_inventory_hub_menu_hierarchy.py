from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "inventory_hub_hierarchy_realign"
CATALOG_VERSION = "inventory_hub_hierarchy_2026_07_15"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")


GROUP_SPECS = (
    {
        "code": "reports.inventory.setup",
        "name": "Setup",
        "route_name": "reports-inventory-setup",
        "icon": "gear",
        "sort_order": 1,
    },
    {
        "code": "reports.inventory.operations",
        "name": "Operations",
        "route_name": "reports-inventory-operations",
        "icon": "boxes",
        "sort_order": 2,
    },
    {
        "code": "reports.inventory.analysis",
        "name": "Analysis Reports",
        "route_name": "reports-inventory-analysis",
        "icon": "bar-chart",
        "sort_order": 3,
    },
    {
        "code": "reports.inventory.controls",
        "name": "Control Reports",
        "route_name": "reports-inventory-controls",
        "icon": "sliders",
        "sort_order": 4,
    },
)


MENU_REPARENT_SPECS = (
    ("reports.inventory.location_master", "reports.inventory.setup", 1),
    ("reports.inventory.settings", "reports.inventory.setup", 2),
    ("reports.inventory.transfer_entry", "reports.inventory.operations", 1),
    ("reports.inventory.transfer_browser", "reports.inventory.operations", 2),
    ("reports.inventory.adjustment_entry", "reports.inventory.operations", 3),
    ("reports.inventory.adjustment_browser", "reports.inventory.operations", 4),
    ("reports.inventory.stock_summary", "reports.inventory.analysis", 1),
    ("reports.inventory.stock_ledger", "reports.inventory.analysis", 2),
    ("reports.inventory.stock_aging", "reports.inventory.analysis", 3),
    ("reports.inventory.location_stock", "reports.inventory.analysis", 4),
    ("reports.inventory.stock_movement", "reports.inventory.analysis", 5),
    ("reports.inventory.stock_day_book", "reports.inventory.analysis", 6),
    ("reports.inventory.stock_book_summary", "reports.inventory.analysis", 7),
    ("reports.inventory.stock_book_detail", "reports.inventory.analysis", 8),
    ("reports.inventory.non_moving_stock", "reports.inventory.controls", 1),
    ("reports.inventory.reorder_status", "reports.inventory.controls", 2),
    ("reports.inventory.slow_moving_dead_stock", "reports.inventory.controls", 3),
)


def _ensure_group(Menu, parent_menu, spec):
    menu, _ = Menu.objects.update_or_create(
        code=spec["code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": spec["name"],
            "menu_type": "group",
            "route_path": "",
            "route_name": spec["route_name"],
            "icon": spec["icon"],
            "sort_order": spec["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": spec["code"],
                "inventory_section": True,
            },
            "isactive": True,
        },
    )
    return menu


def _upsert_inventory_settings_permission(Permission):
    permission, _ = Permission.objects.update_or_create(
        code="inventory.settings.view",
        defaults={
            "name": "View Inventory Settings",
            "module": "inventory",
            "resource": "settings",
            "action": "view",
            "description": "View Inventory Settings",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": "inventory.settings.view",
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

    inventory_hub = Menu.objects.filter(code="reports.inventory", isactive=True).first()
    if inventory_hub is None:
        return

    groups_by_code = {}
    for spec in GROUP_SPECS:
        groups_by_code[spec["code"]] = _ensure_group(Menu, inventory_hub, spec)

    for menu_code, parent_code, sort_order in MENU_REPARENT_SPECS:
        menu = Menu.objects.filter(code=menu_code, isactive=True).first()
        parent_menu = groups_by_code.get(parent_code)
        if menu is None or parent_menu is None:
            continue

        metadata = dict(menu.metadata or {})
        metadata["seed"] = SEED_TAG
        metadata["catalog_version"] = CATALOG_VERSION
        metadata["inventory_section"] = parent_code
        menu.parent_id = parent_menu.id
        menu.sort_order = sort_order
        menu.metadata = metadata
        menu.save(update_fields=["parent_id", "sort_order", "metadata"])

    settings_menu = Menu.objects.filter(code="reports.inventory.settings", isactive=True).first()
    if settings_menu is not None:
        settings_permission = _upsert_inventory_settings_permission(Permission)
        metadata = dict(settings_menu.metadata or {})
        metadata["seed"] = SEED_TAG
        metadata["catalog_version"] = CATALOG_VERSION
        metadata["permission_code"] = "inventory.settings.view"
        settings_menu.metadata = metadata
        settings_menu.save(update_fields=["metadata"])

        MenuPermission.objects.filter(
            menu_id=settings_menu.id,
            relation_type=MENU_RELATION_VISIBILITY,
        ).exclude(permission_id=settings_permission.id).delete()
        MenuPermission.objects.update_or_create(
            menu_id=settings_menu.id,
            permission_id=settings_permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        role_ids = list(
            Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True)
        )
        existing_pairs = set(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                permission_id=settings_permission.id,
            ).values_list("role_id", "permission_id")
        )
        rows = [
            RolePermission(
                role_id=role_id,
                permission_id=settings_permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in role_ids
            if (role_id, settings_permission.id) not in existing_pairs
        ]
        if rows:
            RolePermission.objects.bulk_create(rows)


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0133_add_manufacturing_route_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
