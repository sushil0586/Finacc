from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "capital_distribution_phase1_permissions"
CATALOG_VERSION = "capital_distribution_phase1_2026_09_10"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

PERMISSIONS = (
    ("capital_distribution.setup.view", "View Formation Setup", "setup", "view"),
    ("capital_distribution.setup.manage", "Manage Formation Setup", "setup", "manage"),
    ("capital_distribution.policy.view", "View Distribution Policies", "policy", "view"),
    ("capital_distribution.policy.manage", "Manage Distribution Policies", "policy", "manage"),
    ("capital_distribution.policy.submit", "Submit Distribution Policies", "policy", "submit"),
    ("capital_distribution.policy.approve", "Approve Distribution Policies", "policy", "approve"),
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, resource, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "capital_distribution",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    RolePermission.objects.bulk_create(
        [
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in role_ids
            for permission_id in permission_ids
            if (role_id, permission_id) not in existing
        ]
    )

    parent = Menu.objects.filter(code="accounts.settings", isactive=True).first()
    view_permission = Permission.objects.get(code="capital_distribution.setup.view")
    if parent:
        menu, _ = Menu.objects.update_or_create(
            code="accounts.capital_distribution_setup",
            defaults={
                "parent_id": parent.id,
                "name": "Capital & Distribution",
                "menu_type": "screen",
                "route_path": "capital-distribution-setup",
                "route_name": "capital-distribution-setup",
                "icon": "diagram-3",
                "sort_order": 5,
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "feature": "feature_financial",
                    "access_mode": "setup",
                },
                "isactive": True,
            },
        )
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=view_permission.id,
            relation_type="visibility",
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = list(
        Permission.objects.filter(code__in=[row[0] for row in PERMISSIONS]).values_list("id", flat=True)
    )
    menu_ids = list(
        Menu.objects.filter(code="accounts.capital_distribution_setup").values_list("id", flat=True)
    )
    MenuPermission.objects.filter(menu_id__in=menu_ids).delete()
    Menu.objects.filter(id__in=menu_ids, metadata__seed=SEED_TAG).delete()
    RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0144_add_financial_control_action_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
