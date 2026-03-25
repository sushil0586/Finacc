from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "gstr1_report_menu_2026_03_25"
SEED_NAME = "gstr1_report_menu"

PARENT_CANDIDATES = ["reports.compliance", "reports"]
MENU_CODE = "reports.gstr1report"
PERMISSION_CODE = "reports.gstr1report.view"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent = None
    for code in PARENT_CANDIDATES:
        parent = Menu.objects.filter(code=code).first()
        if parent:
            break

    menu, _ = Menu.objects.update_or_create(
        code=MENU_CODE,
        defaults={
            "parent_id": parent.id if parent else None,
            "name": "GSTR-1 Outward",
            "menu_type": "screen",
            "route_path": "gstreport",
            "route_name": "gstreport",
            "icon": "file-spreadsheet",
            "sort_order": 1,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
                "module": "reports",
                "report_code": "gstr1",
            },
            "isactive": True,
        },
    )

    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "View GSTR-1 Outward Report",
            "module": "reports",
            "resource": "gstr1report",
            "action": "view",
            "description": "Access GSTR-1 outward sales return report",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_NAME,
                "catalog_version": CATALOG_VERSION,
            },
            "isactive": True,
        },
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = list(
        Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True)
    )
    if not role_ids:
        return

    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id)
        .values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in role_ids:
        if (role_id, permission.id) in existing:
            continue
        inserts.append(
            RolePermission(
                role_id=role_id,
                permission_id=permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={
                    "seed": SEED_NAME,
                    "catalog_version": CATALOG_VERSION,
                },
                isactive=True,
            )
        )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    menu_ids = list(Menu.objects.filter(code=MENU_CODE).values_list("id", flat=True))
    permission_ids = list(Permission.objects.filter(code=PERMISSION_CODE).values_list("id", flat=True))

    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_NAME).delete()
        MenuPermission.objects.filter(menu_id__in=menu_ids, permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()

    if menu_ids:
        Menu.objects.filter(id__in=menu_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0033_add_financial_master_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
