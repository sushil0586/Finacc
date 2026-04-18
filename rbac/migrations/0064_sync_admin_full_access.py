from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
SEED_TAG = "admin_full_access_reconcile_2026_04_18"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(isactive=True).values_list("id", flat=True))
    if not permission_ids:
        return

    roles = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).only("id"))
    if not roles:
        return

    existing_rows = {
        (row.role_id, row.permission_id): row
        for row in RolePermission.objects.filter(
            role_id__in=[role.id for role in roles],
            permission_id__in=permission_ids,
        )
    }

    inserts = []
    for role in roles:
        for permission_id in permission_ids:
            row = existing_rows.get((role.id, permission_id))
            if row is None:
                inserts.append(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": SEED_TAG},
                        isactive=True,
                    )
                )
                continue
            metadata = row.metadata or {}
            changed = False
            if row.effect != ROLE_PERMISSION_ALLOW:
                row.effect = ROLE_PERMISSION_ALLOW
                changed = True
            if not row.isactive:
                row.isactive = True
                changed = True
            if metadata.get("seed") != SEED_TAG:
                metadata["seed"] = SEED_TAG
                row.metadata = metadata
                changed = True
            if changed:
                update_fields = ["effect", "isactive", "metadata"]
                if hasattr(row, "updated_at"):
                    update_fields.append("updated_at")
                row.save(update_fields=update_fields)

    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    # This migration is a reconciliation safety net for admin-equivalent roles.
    # Removing grants automatically could strip intentionally retained access.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0063_add_inventory_settings_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
