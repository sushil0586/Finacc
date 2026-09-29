from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "inventory_ops_workflow_repair_2026_09_29"

ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "inventory_user",
)

PERMISSION_SPECS = (
    ("inventory.location.create", "Create Inventory Location", "location", "create"),
    ("inventory.location.update", "Update Inventory Location", "location", "update"),
    ("inventory.location.delete", "Delete Inventory Location", "location", "delete"),
    ("inventory.transfer.create", "Create Inventory Transfer", "transfer", "create"),
    ("inventory.transfer.update", "Update Inventory Transfer", "transfer", "update"),
    ("inventory.transfer.post", "Post Inventory Transfer", "transfer", "post"),
    ("inventory.transfer.unpost", "Unpost Inventory Transfer", "transfer", "unpost"),
    ("inventory.transfer.cancel", "Cancel Inventory Transfer", "transfer", "cancel"),
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    role_ids = list(Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids:
        return

    for code, label, resource, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": label,
                "module": "inventory",
                "resource": resource,
                "action": action,
                "description": label,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )

        existing_rows = {
            row.role_id: row
            for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id)
        }

        inserts = []
        for role_id in role_ids:
            row = existing_rows.get(role_id)
            if row is None:
                inserts.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission.id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": SEED_TAG},
                        isactive=True,
                    )
                )
                continue

            changed = False
            metadata = row.metadata or {}
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
                row.save(update_fields=["effect", "isactive", "metadata"])

        if inserts:
            RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0208_repair_inventory_report_export_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
