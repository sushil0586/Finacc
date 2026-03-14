from django.db import migrations


SALES_MENU_CODE = "sales"
SALES_MENU_NAME = "Sales"
MENU_RELATION_VISIBILITY = "visibility"
ROLE_LEVEL_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"

SALES_SETTINGS_SPEC = {
    "name": "Sales Settings",
    "code": "sales-settings",
    "route": "sales-settings",
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


def forwards(apps, schema_editor):
    MainMenu = apps.get_model("Authentication", "MainMenu")
    Submenu = apps.get_model("Authentication", "Submenu")
    LegacyRole = apps.get_model("entity", "Role")
    RolePrivilege = apps.get_model("entity", "RolePrivilege")
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RBACRole = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    sales_menu = (
        MainMenu.objects.filter(menucode__iexact=SALES_MENU_CODE).order_by("order", "id").first()
        or MainMenu.objects.filter(mainmenu__iexact=SALES_MENU_NAME).order_by("order", "id").first()
    )
    if sales_menu is None:
        sales_menu = MainMenu.objects.create(
            mainmenu=SALES_MENU_NAME,
            menuurl=SALES_MENU_CODE,
            menucode=SALES_MENU_CODE,
            order=(MainMenu.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1,
        )

    submenu = (
        Submenu.objects.filter(submenucode__iexact=SALES_SETTINGS_SPEC["code"]).order_by("id").first()
        or Submenu.objects.filter(subMenuurl__iexact=SALES_SETTINGS_SPEC["route"]).order_by("id").first()
        or Submenu.objects.filter(submenu__iexact=SALES_SETTINGS_SPEC["name"]).order_by("id").first()
    )
    if submenu is None:
        next_order = (
            (Submenu.objects.filter(mainmenu_id=sales_menu.id).order_by("-order").values_list("order", flat=True).first() or 0)
            + 1
        )
        submenu = Submenu.objects.create(
            mainmenu_id=sales_menu.id,
            submenu=SALES_SETTINGS_SPEC["name"],
            submenucode=SALES_SETTINGS_SPEC["code"],
            subMenuurl=SALES_SETTINGS_SPEC["route"],
            order=next_order,
        )
    else:
        submenu.mainmenu_id = sales_menu.id
        submenu.submenu = SALES_SETTINGS_SPEC["name"]
        submenu.submenucode = SALES_SETTINGS_SPEC["code"]
        submenu.subMenuurl = SALES_SETTINGS_SPEC["route"]
        if not submenu.order:
            submenu.order = (
                (Submenu.objects.filter(mainmenu_id=sales_menu.id).order_by("-order").values_list("order", flat=True).first() or 0)
                + 1
            )
        submenu.save(update_fields=["mainmenu", "submenu", "submenucode", "subMenuurl", "order"])

    root_menu, _ = Menu.objects.update_or_create(
        code=_legacy_main_menu_code(sales_menu.id),
        defaults={
            "name": sales_menu.mainmenu,
            "route_path": sales_menu.menuurl or "",
            "route_name": sales_menu.menucode or "",
            "sort_order": _safe_order(sales_menu.order),
            "menu_type": "group",
            "is_system_menu": True,
            "metadata": {"legacy_mainmenu_id": sales_menu.id},
            "isactive": True,
        },
    )
    root_permission, _ = Permission.objects.update_or_create(
        code=_legacy_main_menu_permission_code(sales_menu.id),
        defaults={
            "name": f"{sales_menu.mainmenu} Menu Access",
            "module": sales_menu.menucode or "legacy",
            "resource": "menu",
            "action": "access",
            "description": f"Access to {sales_menu.mainmenu} menu",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {"legacy_mainmenu_id": sales_menu.id},
            "isactive": True,
        },
    )
    MenuPermission.objects.update_or_create(
        menu_id=root_menu.id,
        permission_id=root_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    child_menu, _ = Menu.objects.update_or_create(
        code=_legacy_sub_menu_code(submenu.id),
        defaults={
            "parent_id": root_menu.id,
            "name": submenu.submenu,
            "route_path": submenu.subMenuurl or "",
            "route_name": submenu.submenucode or "",
            "sort_order": _safe_order(submenu.order),
            "menu_type": "screen",
            "is_system_menu": True,
            "metadata": {"legacy_submenu_id": submenu.id, "legacy_mainmenu_id": sales_menu.id},
            "isactive": True,
        },
    )
    child_permission, _ = Permission.objects.update_or_create(
        code=_legacy_sub_menu_permission_code(submenu.id),
        defaults={
            "name": f"{submenu.submenu} Access",
            "module": sales_menu.menucode or "legacy",
            "resource": submenu.submenucode or "submenu",
            "action": "access",
            "description": f"Access to {submenu.submenu}",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {"legacy_submenu_id": submenu.id, "legacy_mainmenu_id": sales_menu.id},
            "isactive": True,
        },
    )
    MenuPermission.objects.update_or_create(
        menu_id=child_menu.id,
        permission_id=child_permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    existing_sales_submenu_ids = list(
        Submenu.objects.filter(mainmenu_id=sales_menu.id).exclude(id=submenu.id).values_list("id", flat=True)
    )

    legacy_roles = {}
    seeded_role_ids = set()
    if existing_sales_submenu_ids:
        sales_roles = LegacyRole.objects.filter(
            id__in=RolePrivilege.objects.filter(submenu_id__in=existing_sales_submenu_ids).values_list("role_id", flat=True)
        )
        for role in sales_roles:
            legacy_roles[role.id] = role
            seeded_role_ids.add(role.id)

    for role in LegacyRole.objects.filter(rolename__iexact="Admin"):
        legacy_roles[role.id] = role
        seeded_role_ids.add(role.id)

    existing_privileges = set(
        RolePrivilege.objects.filter(role_id__in=seeded_role_ids, submenu_id=submenu.id).values_list("role_id", "submenu_id")
    )
    missing_privileges = [
        RolePrivilege(role_id=role.id, submenu_id=submenu.id, entity_id=role.entity_id)
        for role in legacy_roles.values()
        if (role.id, submenu.id) not in existing_privileges
    ]
    if missing_privileges:
        RolePrivilege.objects.bulk_create(missing_privileges)

    legacy_rbac_roles = {}
    for legacy_role in legacy_roles.values():
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
                "isactive": True,
            },
        )
        legacy_rbac_roles[legacy_role.id] = rbac_role.id

    super_admin_roles = list(RBACRole.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    target_role_ids = list(legacy_rbac_roles.values()) + super_admin_roles
    existing_role_permissions = set(
        RolePermission.objects.filter(role_id__in=target_role_ids, permission_id=child_permission.id).values_list("role_id", "permission_id")
    )

    missing_role_permissions = []
    for role_id in legacy_rbac_roles.values():
        if (role_id, child_permission.id) not in existing_role_permissions:
            missing_role_permissions.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=child_permission.id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "sales_settings_menu"},
                    isactive=True,
                )
            )

    for role_id in super_admin_roles:
        if (role_id, child_permission.id) not in existing_role_permissions:
            missing_role_permissions.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=child_permission.id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "sales_settings_menu"},
                    isactive=True,
                )
            )

    if missing_role_permissions:
        RolePermission.objects.bulk_create(missing_role_permissions)


def backwards(apps, schema_editor):
    Submenu = apps.get_model("Authentication", "Submenu")
    RolePrivilege = apps.get_model("entity", "RolePrivilege")
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    submenu_ids = list(
        Submenu.objects.filter(submenucode__iexact=SALES_SETTINGS_SPEC["code"]).values_list("id", flat=True)
    )
    permission_codes = [_legacy_sub_menu_permission_code(submenu_id) for submenu_id in submenu_ids]
    menu_codes = [_legacy_sub_menu_code(submenu_id) for submenu_id in submenu_ids]

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
        ("rbac", "0013_seed_final_menu_catalog"),
        ("Authentication", "0003_authotp_authsession_refresh_fields"),
        ("entity", "0003_alter_userrole_options"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
