from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"


MENU_SPECS = [
    {
        "code": "assets",
        "name": "Assets",
        "menu_type": "group",
        "route_path": "",
        "route_name": "assets",
        "sort_order": 60,
        "parent_code": None,
        "permission": ("assets.menu.access", "Assets Menu Access", "assets", "menu", "access"),
    },
    {
        "code": "assets.registry",
        "name": "Registry",
        "menu_type": "group",
        "route_path": "",
        "route_name": "assets-registry",
        "sort_order": 1,
        "parent_code": "assets",
        "permission": ("assets.registry.access", "Assets Registry Access", "assets", "registry", "access"),
    },
    {
        "code": "assets.depreciation",
        "name": "Depreciation",
        "menu_type": "group",
        "route_path": "",
        "route_name": "assets-depreciation",
        "sort_order": 2,
        "parent_code": "assets",
        "permission": ("assets.depreciation.access", "Assets Depreciation Access", "assets", "depreciation", "access"),
    },
    {
        "code": "assets.controls",
        "name": "Controls",
        "menu_type": "group",
        "route_path": "",
        "route_name": "assets-controls",
        "sort_order": 3,
        "parent_code": "assets",
        "permission": ("assets.controls.access", "Assets Controls Access", "assets", "controls", "access"),
    },
    {
        "code": "assets.registry.asset-master",
        "name": "Asset Master",
        "menu_type": "screen",
        "route_path": "asset-master",
        "route_name": "asset-master",
        "sort_order": 1,
        "parent_code": "assets.registry",
        "permission": ("assets.asset_master.view", "View Asset Master", "assets", "asset_master", "view"),
    },
    {
        "code": "assets.registry.fixed-asset-register",
        "name": "Fixed Asset Register",
        "menu_type": "screen",
        "route_path": "fixed-asset-register",
        "route_name": "fixed-asset-register",
        "sort_order": 2,
        "parent_code": "assets.registry",
        "permission": ("assets.fixed_asset_register.view", "View Fixed Asset Register", "assets", "fixed_asset_register", "view"),
    },
    {
        "code": "assets.registry.asset-history",
        "name": "Asset History",
        "menu_type": "screen",
        "route_path": "asset-history",
        "route_name": "asset-history",
        "sort_order": 3,
        "parent_code": "assets.registry",
        "permission": ("assets.asset_history.view", "View Asset History", "assets", "asset_history", "view"),
    },
    {
        "code": "assets.depreciation.depreciation-run",
        "name": "Depreciation Run",
        "menu_type": "screen",
        "route_path": "depreciation-run",
        "route_name": "depreciation-run",
        "sort_order": 1,
        "parent_code": "assets.depreciation",
        "permission": ("assets.depreciation_run.view", "View Depreciation Run", "assets", "depreciation_run", "view"),
    },
    {
        "code": "assets.depreciation.depreciation-schedule",
        "name": "Depreciation Schedule",
        "menu_type": "screen",
        "route_path": "depreciation-schedule",
        "route_name": "depreciation-schedule",
        "sort_order": 2,
        "parent_code": "assets.depreciation",
        "permission": ("assets.depreciation_schedule.view", "View Depreciation Schedule", "assets", "depreciation_schedule", "view"),
    },
    {
        "code": "assets.controls.asset-events",
        "name": "Asset Events",
        "menu_type": "screen",
        "route_path": "asset-events",
        "route_name": "asset-events",
        "sort_order": 1,
        "parent_code": "assets.controls",
        "permission": ("assets.asset_events.view", "View Asset Events", "assets", "asset_events", "view"),
    },
    {
        "code": "assets.controls.asset-settings",
        "name": "Asset Settings",
        "menu_type": "screen",
        "route_path": "asset-settings",
        "route_name": "asset-settings",
        "sort_order": 2,
        "parent_code": "assets.controls",
        "permission": ("assets.asset_settings.view", "View Asset Settings", "assets", "asset_settings", "view"),
    },
    {
        "code": "catalog",
        "name": "Catalog",
        "menu_type": "group",
        "route_path": "",
        "route_name": "catalog",
        "sort_order": 61,
        "parent_code": None,
        "permission": ("catalog.menu.access", "Catalog Menu Access", "catalog", "menu", "access"),
    },
    {
        "code": "catalog.masters",
        "name": "Masters",
        "menu_type": "group",
        "route_path": "",
        "route_name": "catalog-masters",
        "sort_order": 1,
        "parent_code": "catalog",
        "permission": ("catalog.masters.access", "Catalog Masters Access", "catalog", "masters", "access"),
    },
    {
        "code": "catalog.masters.catalog-products",
        "name": "Products",
        "menu_type": "screen",
        "route_path": "catalog-products",
        "route_name": "catalog-products",
        "sort_order": 1,
        "parent_code": "catalog.masters",
        "permission": ("catalog.products.view", "View Catalog Products", "catalog", "products", "view"),
    },
    {
        "code": "catalog.masters.catalog-product-categories",
        "name": "Product Categories",
        "menu_type": "screen",
        "route_path": "catalog-product-categories",
        "route_name": "catalog-product-categories",
        "sort_order": 2,
        "parent_code": "catalog.masters",
        "permission": ("catalog.product_categories.view", "View Product Categories", "catalog", "product_categories", "view"),
    },
    {
        "code": "catalog.masters.catalog-brands",
        "name": "Brands",
        "menu_type": "screen",
        "route_path": "catalog-brands",
        "route_name": "catalog-brands",
        "sort_order": 3,
        "parent_code": "catalog.masters",
        "permission": ("catalog.brands.view", "View Catalog Brands", "catalog", "brands", "view"),
    },
    {
        "code": "catalog.masters.catalog-uoms",
        "name": "UOMs",
        "menu_type": "screen",
        "route_path": "catalog-uoms",
        "route_name": "catalog-uoms",
        "sort_order": 4,
        "parent_code": "catalog.masters",
        "permission": ("catalog.uoms.view", "View Catalog UOMs", "catalog", "uoms", "view"),
    },
    {
        "code": "catalog.masters.catalog-hsn-sac",
        "name": "HSN / SAC",
        "menu_type": "screen",
        "route_path": "catalog-hsn-sac",
        "route_name": "catalog-hsn-sac",
        "sort_order": 5,
        "parent_code": "catalog.masters",
        "permission": ("catalog.hsn_sac.view", "View Catalog HSN SAC", "catalog", "hsn_sac", "view"),
    },
    {
        "code": "catalog.masters.catalog-price-lists",
        "name": "Price Lists",
        "menu_type": "screen",
        "route_path": "catalog-price-lists",
        "route_name": "catalog-price-lists",
        "sort_order": 6,
        "parent_code": "catalog.masters",
        "permission": ("catalog.price_lists.view", "View Catalog Price Lists", "catalog", "price_lists", "view"),
    },
    {
        "code": "catalog.masters.catalog-product-attributes",
        "name": "Product Attributes",
        "menu_type": "screen",
        "route_path": "catalog-product-attributes",
        "route_name": "catalog-product-attributes",
        "sort_order": 7,
        "parent_code": "catalog.masters",
        "permission": ("catalog.product_attributes.view", "View Catalog Product Attributes", "catalog", "product_attributes", "view"),
    },
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_map = {}
    permission_ids = []

    for spec in MENU_SPECS:
        parent = menu_map.get(spec["parent_code"])
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent.id if parent else None,
                "name": spec["name"],
                "menu_type": spec["menu_type"],
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "sort_order": spec["sort_order"],
                "icon": "",
                "is_system_menu": False,
                "metadata": {"seed": "asset_catalog_compact_menus"},
                "isactive": True,
            },
        )
        menu_map[spec["code"]] = menu

        permission_code, permission_name, module, resource, action = spec["permission"]
        permission, _ = Permission.objects.update_or_create(
            code=permission_code,
            defaults={
                "name": permission_name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": permission_name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": False,
                "metadata": {"seed": "asset_catalog_compact_menus", "menu_code": spec["code"]},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)
        MenuPermission.objects.get_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    super_admin_roles = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=super_admin_roles,
            permission_id__in=permission_ids,
        ).values_list("role_id", "permission_id")
    )
    missing_role_permissions = []
    for role_id in super_admin_roles:
        for permission_id in permission_ids:
            key = (role_id, permission_id)
            if key in existing_pairs:
                continue
            missing_role_permissions.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "asset_catalog_compact_menus"},
                    isactive=True,
                )
            )
    if missing_role_permissions:
        RolePermission.objects.bulk_create(missing_role_permissions)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_codes = [spec["code"] for spec in MENU_SPECS]
    permission_codes = [spec["permission"][0] for spec in MENU_SPECS]

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0010_sync_asset_menu_routes"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
