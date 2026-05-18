from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "payroll_runtime_readiness_menu"
CATALOG_VERSION = "payroll_runtime_readiness_menu_2026_05_17"
ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "payroll_operator",
    "payroll_read_only_reviewer",
)

PERMISSION_CODE = "payroll.runtime_readiness.view"
MENU_CODE = "payroll.runtime-readiness"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    root_menu = Menu.objects.get(code="payroll")
    permission, _ = Permission.objects.update_or_create(
        code=PERMISSION_CODE,
        defaults={
            "name": "View Payroll Runtime Readiness",
            "module": "payroll",
            "resource": "runtime_readiness",
            "action": "view",
            "description": "View Payroll Runtime Readiness",
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_CODE,
            },
            "isactive": True,
        },
    )

    menu, _ = Menu.objects.update_or_create(
        code=MENU_CODE,
        defaults={
            "parent_id": root_menu.id,
            "name": "Payroll Readiness",
            "menu_type": "screen",
            "route_path": "/payroll/runtime/readiness",
            "route_name": "payroll-runtime-readiness",
            "icon": "clipboard-check",
            "sort_order": 15,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_CODE,
                "route_path": "/payroll/runtime/readiness",
                "feature": "feature_payroll",
                "access_mode": "setup",
                "menu_group": "payroll",
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

    role_ids = list(Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing_pairs = set(RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", "permission_id"))
    inserts = []
    for role_id in role_ids:
        if (role_id, permission.id) in existing_pairs:
            continue
        inserts.append(
            RolePermission(
                role_id=role_id,
                permission_id=permission.id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
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

    permission_ids = list(Permission.objects.filter(code=PERMISSION_CODE).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code=MENU_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0119_add_payroll_statutory_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
