from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "manufacturing_workorder_workflow_repair_2026_09_29"

ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "manufacturing_user",
)

PERMISSION_SPECS = (
    ("manufacturing.workorder.view", "View Manufacturing Work Order", "view"),
    ("manufacturing.workorder.create", "Create Manufacturing Work Order", "create"),
    ("manufacturing.workorder.update", "Update Manufacturing Work Order", "update"),
    ("manufacturing.workorder.operate", "Operate Manufacturing Work Order", "operate"),
    ("manufacturing.workorder.qc_approve", "Approve Manufacturing Work Order QC", "qc_approve"),
    ("manufacturing.workorder.post", "Post Manufacturing Work Order", "post"),
    ("manufacturing.workorder.unpost", "Unpost Manufacturing Work Order", "unpost"),
    ("manufacturing.workorder.cancel", "Cancel Manufacturing Work Order", "cancel"),
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, label, action in PERMISSION_SPECS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": label,
                "module": "manufacturing",
                "resource": "workorder",
                "action": action,
                "description": label,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids or not permission_ids:
        return

    existing_rows = {
        (row.role_id, row.permission_id): row
        for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
    }

    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            row = existing_rows.get((role_id, permission_id))
            if row is None:
                inserts.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
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
    dependencies = [("rbac", "0206_repair_manufacturing_inventory_crud_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
