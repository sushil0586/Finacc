from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
SEED_TAG = "admin_self_service_permissions"
CATALOG_VERSION = "admin_self_service_permissions_2026_08_26"


PERMISSION_SPECS = [
    ("admin.menu.view", "View Menu Access Setup", "menu", "view"),
    ("admin.menu.update", "Update Menu Access Setup", "menu", "update"),
    ("admin.role_access.view", "View Role Access Matrix", "role_access", "view"),
    ("admin.role_access.update", "Update Role Access Matrix", "role_access", "update"),
    ("admin.user_access.view", "View User Access Assignments", "user_access", "view"),
    ("admin.user_access.update", "Update User Access Assignments", "user_access", "update"),
    ("admin.access_preview.view", "Preview Effective Access", "access_preview", "view"),
    ("admin.audit_log.view", "View RBAC Audit Logs", "audit_log", "view"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, resource, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "admin",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "launch_reason": "customer_admin_user_management_self_service",
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids:
        return

    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=role_ids,
            permission_id__in=permission_ids,
        ).values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code__in=[spec[0] for spec in PERMISSION_SPECS]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0139_add_hrms_runtime_menus_and_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
