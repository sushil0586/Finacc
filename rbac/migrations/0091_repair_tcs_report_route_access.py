from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    reports_root = Menu.objects.filter(code="reports").first()
    if not reports_root:
        reports_root = Menu.objects.create(
            code="reports",
            name="Reports",
            menu_type="group",
            route_path="",
            route_name="reports",
            sort_order=80,
            icon="bar-chart-3",
            is_system_menu=True,
            metadata={"seed": "repair_tcs_report_route_access"},
            isactive=True,
        )
    elif not reports_root.isactive:
        reports_root.isactive = True
        reports_root.save(update_fields=["isactive", "updated_at"])

    reports_compliance, _ = Menu.objects.update_or_create(
        code="reports.compliance",
        defaults={
            "parent_id": reports_root.id,
            "name": "Compliance Reports",
            "menu_type": "group",
            "route_path": "",
            "route_name": "reports-compliance",
            "sort_order": 2,
            "icon": "file-search",
            "is_system_menu": True,
            "metadata": {"seed": "repair_tcs_report_route_access"},
            "isactive": True,
        },
    )

    permission_specs = [
        ("reports.compliance.access", "Access Compliance Reports", "reports", "compliance", "access"),
        ("reports.tcsledgerreport.view", "View TCS Ledger", "reports", "tcsledgerreport", "view"),
        ("reports.tcsfilingpack.view", "View TCS Filing Pack", "reports", "tcsfilingpack", "view"),
    ]
    permissions = {}
    for code, name, module, resource, action in permission_specs:
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
                "metadata": {"seed": "repair_tcs_report_route_access"},
                "isactive": True,
            },
        )
        if not permission.isactive:
            permission.isactive = True
            permission.save(update_fields=["isactive", "updated_at"])
        permissions[code] = permission

    menu_specs = [
        ("reports.tcsledgerreport", "TCS Ledger", "tcsledgerreport", "tcsledgerreport", 4, "book-a", permissions["reports.tcsledgerreport.view"]),
        ("reports.tcsfilingpack", "TCS Filing Pack", "tcsfilingpack", "tcsfilingpack", 5, "briefcase", permissions["reports.tcsfilingpack.view"]),
    ]
    screen_menus = []
    for code, name, route_path, route_name, sort_order, icon, permission in menu_specs:
        menu, _ = Menu.objects.update_or_create(
            code=code,
            defaults={
                "parent_id": reports_compliance.id,
                "name": name,
                "menu_type": "screen",
                "route_path": route_path,
                "route_name": route_name,
                "sort_order": sort_order,
                "icon": icon,
                "is_system_menu": True,
                "metadata": {"seed": "repair_tcs_report_route_access"},
                "isactive": True,
            },
        )
        if not menu.isactive:
            menu.isactive = True
            menu.save(update_fields=["isactive", "updated_at"])
        screen_menus.append((menu, permission))

    MenuPermission.objects.update_or_create(
        menu_id=reports_compliance.id,
        permission_id=permissions["reports.compliance.access"].id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )
    for menu, permission in screen_menus:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

    source_permission_codes = [
        "compliance.tcsstatutory.view",
        "compliance.tcsreturn27eq.view",
        "reports.tcsledgerreport.view",
        "reports.tcsfilingpack.view",
    ]
    role_ids = set(
        RolePermission.objects.filter(
            isactive=True,
            permission__code__in=source_permission_codes,
            role__isactive=True,
        ).values_list("role_id", flat=True)
    )
    role_ids.update(
        Role.objects.filter(
            isactive=True,
            code__in=["entity.super_admin", "admin", "report_viewer", "compliance_user"],
        ).values_list("id", flat=True)
    )

    target_permission_ids = [
        permissions["reports.compliance.access"].id,
        permissions["reports.tcsledgerreport.view"].id,
        permissions["reports.tcsfilingpack.view"].id,
    ]
    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=role_ids,
            permission_id__in=target_permission_ids,
        ).values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in target_permission_ids:
            if (role_id, permission_id) in existing_pairs:
                RolePermission.objects.filter(role_id=role_id, permission_id=permission_id).update(isactive=True)
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "repair_tcs_report_route_access"},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("rbac", "0090_add_gst_tds_config_menu_and_admin_grants")]

    operations = [migrations.RunPython(forwards, backwards)]
