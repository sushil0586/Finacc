from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "inventory_transfer_action_permissions_2026_04_16"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_specs = [
        ("inventory.transfer.update", "Inventory Transfer Update", "update"),
        ("inventory.transfer.post", "Inventory Transfer Post", "post"),
        ("inventory.transfer.unpost", "Inventory Transfer Unpost", "unpost"),
        ("inventory.transfer.cancel", "Inventory Transfer Cancel", "cancel"),
    ]
    permission_ids: list[int] = []
    for code, name, action in permission_specs:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "inventory",
                "resource": "transfer",
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "inventory_transfer_actions",
                    "catalog_version": CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id")
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
                    metadata={"seed": "inventory_transfer_actions", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [
        "inventory.transfer.update",
        "inventory.transfer.post",
        "inventory.transfer.unpost",
        "inventory.transfer.cancel",
    ]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0061_add_inventory_transfer_browser_menu")]

    operations = [migrations.RunPython(forwards, backwards)]
