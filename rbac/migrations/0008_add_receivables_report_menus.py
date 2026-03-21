from django.db import migrations


REPORT_MENU_CODE = "reports"
REPORT_MENU_NAME = "Reports"
MENU_RELATION_VISIBILITY = "visibility"
ROLE_LEVEL_ENTITY = "entity"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"

RECEIVABLE_REPORTS = (
    {
        "name": "Customer Outstanding",
        "code": "outstandingreport",
        "route": "outstandingreport",
    },
    {
        "name": "Receivable Aging",
        "code": "accountsreceivableaging",
        "route": "accountsreceivableaging",
    },
)


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

    existing_submenu_orders = list(
        Submenu.objects.filter(mainmenu_id=reports_menu.id).values_list("order", flat=True)
    )
    next_order = (max(existing_submenu_orders) if existing_submenu_orders else 0) + 1

    submenus_by_code = {}
    for index, spec in enumerate(RECEIVABLE_REPORTS):
        submenu, _ = Submenu.objects.update_or_create(
            submenucode=spec["code"],
            defaults={
                "mainmenu_id": reports_menu.id,
                "submenu": spec["name"],
                "subMenuurl": spec["route"],
                "order": next_order + index,
            },
        )
        submenus_by_code[spec["code"]] = submenu

    new_submenu_ids = [submenu.id for submenu in submenus_by_code.values()]
    existing_report_submenu_ids = list(
        Submenu.objects.filter(mainmenu_id=reports_menu.id)
        .exclude(id__in=new_submenu_ids)
        .values_list("id", flat=True)
    )

    legacy_roles = {}
    seeded_role_ids = set()
    if existing_report_submenu_ids:
        report_roles = LegacyRole.objects.filter(
            id__in=RolePrivilege.objects.filter(submenu_id__in=existing_report_submenu_ids).values_list("role_id", flat=True)
        )
        for role in report_roles:
            legacy_roles[role.id] = role
            seeded_role_ids.add(role.id)

    for role in LegacyRole.objects.filter(rolename__iexact="Admin"):
        legacy_roles[role.id] = role
        seeded_role_ids.add(role.id)

    existing_privileges = set(
        RolePrivilege.objects.filter(role_id__in=seeded_role_ids, submenu_id__in=new_submenu_ids)
        .values_list("role_id", "submenu_id")
    )
    missing_privileges = []
    for role in legacy_roles.values():
        for submenu in submenus_by_code.values():
            key = (role.id, submenu.id)
            if key in existing_privileges:
                continue
            missing_privileges.append(
                RolePrivilege(role_id=role.id, submenu_id=submenu.id, entity_id=role.entity_id)
            )
    if missing_privileges:
        RolePrivilege.objects.bulk_create(missing_privileges)

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

    submenu_permissions = {}
    for submenu in submenus_by_code.values():
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
                "metadata": {
                    "legacy_submenu_id": submenu.id,
                    "legacy_mainmenu_id": reports_menu.id,
                },
            },
        )
        permission, _ = Permission.objects.update_or_create(
            code=_legacy_sub_menu_permission_code(submenu.id),
            defaults={
                "name": f"{submenu.submenu} Access",
                "module": reports_menu.menucode or "legacy",
                "resource": submenu.submenucode or "submenu",
                "action": "access",
                "description": f"Access to {submenu.submenu}",
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "legacy_submenu_id": submenu.id,
                    "legacy_mainmenu_id": reports_menu.id,
                },
            },
        )
        submenu_permissions[submenu.id] = permission.id
        MenuPermission.objects.get_or_create(
            menu_id=child_menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
        )

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
                "metadata": {
                    "legacy_role_id": legacy_role.id,
                    "legacy_entity_id": legacy_role.entity_id,
                },
            },
        )
        legacy_rbac_roles[legacy_role.id] = rbac_role.id

    existing_role_permissions = set(
        RolePermission.objects.filter(
            role_id__in=list(legacy_rbac_roles.values()),
            permission_id__in=list(submenu_permissions.values()),
        ).values_list("role_id", "permission_id")
    )
    missing_role_permissions = []
    for legacy_role_id, rbac_role_id in legacy_rbac_roles.items():
        granted_submenu_ids = set(
            RolePrivilege.objects.filter(role_id=legacy_role_id, submenu_id__in=new_submenu_ids).values_list("submenu_id", flat=True)
        )
        for submenu_id in granted_submenu_ids:
            key = (rbac_role_id, submenu_permissions[submenu_id])
            if key in existing_role_permissions:
                continue
            missing_role_permissions.append(
                RolePermission(
                    role_id=rbac_role_id,
                    permission_id=submenu_permissions[submenu_id],
                    effect=ROLE_PERMISSION_ALLOW,
                )
            )

    super_admin_roles = list(RBACRole.objects.filter(code="entity.super_admin").values_list("id", flat=True))
    existing_super_admin_permissions = set(
        RolePermission.objects.filter(
            role_id__in=super_admin_roles,
            permission_id__in=list(submenu_permissions.values()),
        ).values_list("role_id", "permission_id")
    )
    for role_id in super_admin_roles:
        for permission_id in submenu_permissions.values():
            key = (role_id, permission_id)
            if key in existing_super_admin_permissions:
                continue
            missing_role_permissions.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                )
            )

    if missing_role_permissions:
        RolePermission.objects.bulk_create(missing_role_permissions)


def backwards(apps, schema_editor):
    # Keep seeded menu and permission rows intact on reverse to avoid breaking live navigation setups.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("Authentication", "0003_authotp_authsession_refresh_fields"),
        ("entity", "0003_alter_userrole_options"),
        ("rbac", "0007_rbacauditlog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
