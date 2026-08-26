from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
CATALOG_VERSION = "inventory_adjustment_action_permissions_2026_08_25"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_specs = [
        ("inventory.adjustment.update", "Inventory Adjustment Update", "update"),
        ("inventory.adjustment.post", "Inventory Adjustment Post", "post"),
        ("inventory.adjustment.unpost", "Inventory Adjustment Unpost", "unpost"),
        ("inventory.adjustment.cancel", "Inventory Adjustment Cancel", "cancel"),
    ]
    permission_ids: list[int] = []
    for code, name, action in permission_specs:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "inventory",
                "resource": "adjustment",
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "inventory_adjustment_actions",
                    "catalog_version": CATALOG_VERSION,
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
                    metadata={"seed": "inventory_adjustment_actions", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [
        "inventory.adjustment.update",
        "inventory.adjustment.post",
        "inventory.adjustment.unpost",
        "inventory.adjustment.cancel",
    ]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0136_normalize_report_menu_sections")]

    operations = [migrations.RunPython(forwards, backwards)]
