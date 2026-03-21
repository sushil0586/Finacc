from django.db import migrations


REPORT_MENU_CODE = "reports"
REPORT_MENU_NAME = "Reports"
MENU_RELATION_VISIBILITY = "visibility"
ROLE_LEVEL_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"

LEGACY_MENU_SPEC = {
    "name": "Asset Category Master",
    "code": "asset-category-master",
    "route": "asset-category-master",
    "legacy_codes": ["assetcategorymaster"],
}

COMPACT_MENU_SPEC = {
    "code": "assets.registry.asset-category-master",
    "name": "Asset Category Master",
    "menu_type": "screen",
    "route_path": "asset-category-master",
    "route_name": "asset-category-master",
    "sort_order": 2,
    "parent_code": "assets.registry",
    "permission": (
        "assets.asset_category_master.view",
        "View Asset Category Master",
        "assets",
        "asset_category_master",
        "view",
    ),
}


def _safe_order(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _legacy_main_menu_code(main_menu_id):
    return f"legacy.mainmenu.{main_menu_id}"


def _legacy_main_menu_permission_code(main_menu_id):
    return f"legacy.mainmenu.{main_menu_id}.access"


def _legacy_sub_menu_code(submenu_id):
    return f"legacy.submenu.{submenu_id}"


def _legacy_sub_menu_permission_code(submenu_id):
    return f"legacy.submenu.{submenu_id}.access"


def _get_model_or_none(apps, app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def forwards(apps, schema_editor):
    MainMenu = _get_model_or_none(apps, "Authentication", "MainMenu")
    Submenu = _get_model_or_none(apps, "Authentication", "Submenu")
    LegacyRole = _get_model_or_none(apps, "entity", "Role")
    RolePrivilege = _get_model_or_none(apps, "entity", "RolePrivilege")
    if not all([Submenu, RolePrivilege]):
        return
    if not all([MainMenu, Submenu, LegacyRole, RolePrivilege]):
        # Legacy menu/role models may not exist on fresh installs.
        return
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RBACRole = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    reports_menu = (
        MainMenu.objects.filter(menucode__iexact=REPORT_MENU_CODE).order_by("order", "id").first()
        or MainMenu.objects.filter(mainmenu__iexact=REPORT_MENU_NAME).order_by("order", "id").first()
    )
    if reports_menu is None:
        reports_menu = MainMenu.objects.create(
            mainmenu=REPORT_MENU_NAME,
            menuurl=REPORT_MENU_CODE,
            menucode=REPORT_MENU_CODE,
            order=(MainMenu.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1,
        )

    submenu = (
        Submenu.objects.filter(submenucode__in=[LEGACY_MENU_SPEC["code"], *LEGACY_MENU_SPEC["legacy_codes"]]).order_by("id").first()
        or Submenu.objects.filter(subMenuurl__in=[LEGACY_MENU_SPEC["route"], *LEGACY_MENU_SPEC["legacy_codes"]]).order_by("id").first()
    )
    if submenu is None:
        next_order = (
            (Submenu.objects.filter(mainmenu_id=reports_menu.id).order_by("-order").values_list("order", flat=True).first() or 0)
            + 1
        )
        submenu = Submenu.objects.create(
            mainmenu_id=reports_menu.id,
            submenu=LEGACY_MENU_SPEC["name"],
            submenucode=LEGACY_MENU_SPEC["code"],
            subMenuurl=LEGACY_MENU_SPEC["route"],
            order=next_order,
        )
    else:
        submenu.mainmenu_id = reports_menu.id
        submenu.submenu = LEGACY_MENU_SPEC["name"]
        submenu.submenucode = LEGACY_MENU_SPEC["code"]
        submenu.subMenuurl = LEGACY_MENU_SPEC["route"]
        if not submenu.order:
            submenu.order = (
                (Submenu.objects.filter(mainmenu_id=reports_menu.id).order_by("-order").values_list("order", flat=True).first() or 0)
                + 1
            )
        submenu.save(update_fields=["mainmenu", "submenu", "submenucode", "subMenuurl", "order"])

    root_menu, _ = Menu.objects.update_or_create(
        code=_legacy_main_menu_code(reports_menu.id),
        defaults={
            "name": reports_menu.mainmenu,
            "route_path": reports_menu.menuurl or "",
            "route_name": reports_menu.menucode or "",
            "sort_order": _safe_order(reports_menu.order),
            "menu_type": "group",
            "is_system_menu": True,
            "metadata": {"legacy_mainmenu_id": reports_menu.id},
        },
    )
    root_permission, _ = Permission.objects.update_or_create(
        code=_legacy_main_menu_permission_code(reports_menu.id),
        defaults={
            "name": f"{reports_menu.mainmenu} Menu Access",
            "module": reports_menu.menucode or "legacy",
            "resource": "menu",
            "action": "access",
            "description": f"Access to {reports_menu.mainmenu} menu",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {"legacy_mainmenu_id": reports_menu.id},
        },
    )
    MenuPermission.objects.get_or_create(
        menu_id=root_menu.id,
        permission_id=root_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
    )

    legacy_child_menu, _ = Menu.objects.update_or_create(
        code=_legacy_sub_menu_code(submenu.id),
        defaults={
            "parent_id": root_menu.id,
            "name": submenu.submenu,
            "route_path": submenu.subMenuurl or "",
            "route_name": submenu.submenucode or "",
            "sort_order": _safe_order(submenu.order),
            "menu_type": "screen",
            "is_system_menu": True,
            "metadata": {"legacy_submenu_id": submenu.id, "legacy_mainmenu_id": reports_menu.id},
        },
    )
    legacy_permission, _ = Permission.objects.update_or_create(
        code=_legacy_sub_menu_permission_code(submenu.id),
        defaults={
            "name": f"{submenu.submenu} Access",
            "module": reports_menu.menucode or "legacy",
            "resource": submenu.submenucode or "submenu",
            "action": "access",
            "description": f"Access to {submenu.submenu}",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {"legacy_submenu_id": submenu.id, "legacy_mainmenu_id": reports_menu.id},
        },
    )
    MenuPermission.objects.get_or_create(
        menu_id=legacy_child_menu.id,
        permission_id=legacy_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
    )

    compact_parent = Menu.objects.filter(code=COMPACT_MENU_SPEC["parent_code"]).first()
    compact_menu, _ = Menu.objects.update_or_create(
        code=COMPACT_MENU_SPEC["code"],
        defaults={
            "parent_id": compact_parent.id if compact_parent else None,
            "name": COMPACT_MENU_SPEC["name"],
            "menu_type": COMPACT_MENU_SPEC["menu_type"],
            "route_path": COMPACT_MENU_SPEC["route_path"],
            "route_name": COMPACT_MENU_SPEC["route_name"],
            "sort_order": COMPACT_MENU_SPEC["sort_order"],
            "icon": "",
            "is_system_menu": False,
            "metadata": {
                "seed": "asset_category_master_menu",
                "aliases": LEGACY_MENU_SPEC["legacy_codes"],
            },
            "isactive": True,
        },
    )
    permission_code, permission_name, module, resource, action = COMPACT_MENU_SPEC["permission"]
    compact_permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": permission_name,
            "module": module,
            "resource": resource,
            "action": action,
            "description": permission_name,
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": False,
            "metadata": {"seed": "asset_category_master_menu", "menu_code": COMPACT_MENU_SPEC["code"]},
            "isactive": True,
        },
    )
    MenuPermission.objects.get_or_create(
        menu_id=compact_menu.id,
        permission_id=compact_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    admin_legacy_roles = list(LegacyRole.objects.filter(rolename__iexact="Admin"))
    existing_privileges = set(
        RolePrivilege.objects.filter(
            role_id__in=[role.id for role in admin_legacy_roles],
            submenu_id=submenu.id,
        ).values_list("role_id", "submenu_id")
    )
    missing_privileges = [
        RolePrivilege(role_id=role.id, submenu_id=submenu.id, entity_id=role.entity_id)
        for role in admin_legacy_roles
        if (role.id, submenu.id) not in existing_privileges
    ]
    if missing_privileges:
        RolePrivilege.objects.bulk_create(missing_privileges)

    legacy_rbac_roles = {}
    for legacy_role in admin_legacy_roles:
        rbac_role, _ = RBACRole.objects.update_or_create(
            entity_id=legacy_role.entity_id,
            code=f"legacy_role_{legacy_role.id}",
            defaults={
                "name": legacy_role.rolename,
                "description": legacy_role.roledesc or "",
                "role_level": ROLE_LEVEL_ENTITY,
                "is_system_role": False,
                "is_assignable": True,
                "priority": legacy_role.rolelevel or 100,
                "metadata": {"legacy_role_id": legacy_role.id, "legacy_entity_id": legacy_role.entity_id},
            },
        )
        legacy_rbac_roles[legacy_role.id] = rbac_role.id

    super_admin_roles = list(RBACRole.objects.filter(code="entity.super_admin").values_list("id", flat=True))
    target_role_ids = list(legacy_rbac_roles.values()) + super_admin_roles
    target_permission_ids = [legacy_permission.id, compact_permission.id]
    existing_role_permissions = set(
        RolePermission.objects.filter(
            role_id__in=target_role_ids,
            permission_id__in=target_permission_ids,
        ).values_list("role_id", "permission_id")
    )

    missing_role_permissions = []
    for role_id in legacy_rbac_roles.values():
        for permission_id in target_permission_ids:
            key = (role_id, permission_id)
            if key in existing_role_permissions:
                continue
            missing_role_permissions.append(
                RolePermission(role_id=role_id, permission_id=permission_id, effect=ROLE_PERMISSION_ALLOW)
            )
    for role_id in super_admin_roles:
        for permission_id in target_permission_ids:
            key = (role_id, permission_id)
            if key in existing_role_permissions:
                continue
            missing_role_permissions.append(
                RolePermission(role_id=role_id, permission_id=permission_id, effect=ROLE_PERMISSION_ALLOW)
            )
    if missing_role_permissions:
        RolePermission.objects.bulk_create(missing_role_permissions)


def backwards(apps, schema_editor):
    Submenu = _get_model_or_none(apps, "Authentication", "Submenu")
    RolePrivilege = _get_model_or_none(apps, "entity", "RolePrivilege")
    if not all([Submenu, RolePrivilege]):
        return
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    submenu_ids = list(
        Submenu.objects.filter(
            submenucode__in=[LEGACY_MENU_SPEC["code"], *LEGACY_MENU_SPEC["legacy_codes"]]
        ).values_list("id", flat=True)
    )
    permission_codes = [COMPACT_MENU_SPEC["permission"][0], *[_legacy_sub_menu_permission_code(submenu_id) for submenu_id in submenu_ids]]
    menu_codes = [COMPACT_MENU_SPEC["code"], *[_legacy_sub_menu_code(submenu_id) for submenu_id in submenu_ids]]

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code__in=menu_codes).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()
    if submenu_ids:
        RolePrivilege.objects.filter(submenu_id__in=submenu_ids).delete()
        Submenu.objects.filter(id__in=submenu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0011_add_asset_catalog_compact_menus"),
        ("Authentication", "0003_authotp_authsession_refresh_fields"),
        ("entity", "0003_alter_userrole_options"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
