from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "modern_only_2026_03"

NEW_MENU_SPECS = [
    {
        "code": "sales.configuration",
        "name": "Configuration",
        "menu_type": "group",
        "route_path": "",
        "route_name": "sales-configuration",
        "sort_order": 2,
        "parent_code": "sales",
        "icon": "settings-2",
    },
    {
        "code": "sales.configuration.settings",
        "name": "Sales Settings",
        "menu_type": "screen",
        "route_path": "sales-settings",
        "route_name": "sales-settings",
        "sort_order": 1,
        "parent_code": "sales.configuration",
        "icon": "sliders-horizontal",
    },
]

MANAGED_ROOT_CODES = ("dashboard", "masters", "sales", "purchase", "accounts", "compliance", "reports", "admin")


def _module_from_code(code):
    return code.split(".", 1)[0]


def _resource_from_code(code):
    return code.split(".")[-1].replace("-", "_")


def _permission_tuple(spec):
    module = _module_from_code(spec["code"])
    if spec["code"] == "sales.configuration.settings":
        return ("sales.settings.view", "View Sales Settings", "sales", "settings", "view")
    resource = _resource_from_code(spec["code"])
    action = "view" if spec["menu_type"] == "screen" else "access"
    name_prefix = "View" if spec["menu_type"] == "screen" else "Access"
    return (f"{module}.{resource}.{action}", f"{name_prefix} {spec['name']}", module, resource, action)


def _safe_update_fields(obj, fields):
    update_fields = list(fields)
    if hasattr(obj, "updated_at") and "updated_at" not in update_fields:
        update_fields.append("updated_at")
    obj.save(update_fields=update_fields)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_map = {menu.code: menu for menu in Menu.objects.filter(code__in=["sales", "sales.configuration"])}
    created_permission_ids = []

    for spec in NEW_MENU_SPECS:
        parent = menu_map.get(spec["parent_code"])
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent.id if parent else None,
                "name": spec["name"],
                "menu_type": spec["menu_type"],
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "modern_rbac_cleanup",
                    "catalog_version": CATALOG_VERSION,
                    "managed_root": _module_from_code(spec["code"]),
                },
                "isactive": True,
            },
        )
        menu_map[spec["code"]] = menu

        permission_code, permission_name, module, resource, action = _permission_tuple(spec)
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
                    "seed": "modern_rbac_cleanup",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                },
                "isactive": True,
            },
        )
        created_permission_ids.append(permission.id)
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=created_permission_ids).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in super_admin_role_ids:
        for permission_id in created_permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "modern_rbac_cleanup", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)

    legacy_permission_ids = list(Permission.objects.filter(code__startswith="legacy.").values_list("id", flat=True))
    legacy_menu_ids = list(Menu.objects.filter(code__startswith="legacy.").values_list("id", flat=True))

    if legacy_permission_ids:
        RolePermission.objects.filter(permission_id__in=legacy_permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=legacy_permission_ids).delete()
        Permission.objects.filter(id__in=legacy_permission_ids).delete()

    if legacy_menu_ids:
        MenuPermission.objects.filter(menu_id__in=legacy_menu_ids).delete()
        Menu.objects.filter(id__in=legacy_menu_ids).delete()

    legacy_roles = Role.objects.filter(code__startswith="legacy_role_")
    for role in legacy_roles:
        if role.isactive:
            role.isactive = False
            _safe_update_fields(role, ["isactive"])

    valid_codes = set(menu.code for menu in Menu.objects.filter(isactive=True).exclude(code__startswith="legacy."))
    for menu in Menu.objects.filter(isactive=True).exclude(code__startswith="legacy."):
        if any(menu.code == root or menu.code.startswith(f"{root}.") for root in MANAGED_ROOT_CODES):
            if menu.code not in valid_codes:
                menu.isactive = False
                _safe_update_fields(menu, ["isactive"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    target_codes = [spec["code"] for spec in NEW_MENU_SPECS]
    permission_codes = [_permission_tuple(spec)[0] for spec in NEW_MENU_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=target_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0014_add_sales_settings_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
