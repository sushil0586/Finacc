from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "sales_workflow_repair_2026_09_30"

ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "sales_user",
    "accounts_manager",
)

SALES_WORKFLOW_PERMISSION_SPECS = (
    ("sales.invoice.view", "View Sales Invoice"),
    ("sales.invoice.create", "Create Sales Invoice"),
    ("sales.invoice.update", "Update Sales Invoice"),
    ("sales.invoice.edit", "Edit Sales Invoice"),
    ("sales.invoice.delete", "Delete Sales Invoice"),
    ("sales.invoice.print", "Print Sales Invoice"),
    ("sales.invoice.confirm", "Confirm Sales Invoice"),
    ("sales.invoice.post", "Post Sales Invoice"),
    ("sales.invoice.unpost", "Unpost Sales Invoice"),
    ("sales.invoice.cancel", "Cancel Sales Invoice"),
    ("sales.credit_note.view", "View Sales Credit Note"),
    ("sales.credit_note.create", "Create Sales Credit Note"),
    ("sales.credit_note.update", "Update Sales Credit Note"),
    ("sales.credit_note.edit", "Edit Sales Credit Note"),
    ("sales.credit_note.delete", "Delete Sales Credit Note"),
    ("sales.credit_note.print", "Print Sales Credit Note"),
    ("sales.credit_note.confirm", "Confirm Sales Credit Note"),
    ("sales.credit_note.post", "Post Sales Credit Note"),
    ("sales.credit_note.unpost", "Unpost Sales Credit Note"),
    ("sales.credit_note.cancel", "Cancel Sales Credit Note"),
    ("sales.debit_note.view", "View Sales Debit Note"),
    ("sales.debit_note.create", "Create Sales Debit Note"),
    ("sales.debit_note.update", "Update Sales Debit Note"),
    ("sales.debit_note.edit", "Edit Sales Debit Note"),
    ("sales.debit_note.delete", "Delete Sales Debit Note"),
    ("sales.debit_note.print", "Print Sales Debit Note"),
    ("sales.debit_note.confirm", "Confirm Sales Debit Note"),
    ("sales.debit_note.post", "Post Sales Debit Note"),
    ("sales.debit_note.unpost", "Unpost Sales Debit Note"),
    ("sales.debit_note.cancel", "Cancel Sales Debit Note"),
)


def _permission_parts(code):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = "_".join(parts[1:-1])
    return module, resource, action


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, label in SALES_WORKFLOW_PERMISSION_SPECS:
        module, resource, action = _permission_parts(code)
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": label,
                "module": module,
                "resource": resource,
                "action": action,
                "description": label,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(
        Role.objects.filter(code__in=ROLE_CODES, isactive=True).values_list(
            "id", flat=True
        )
    )
    if not role_ids or not permission_ids:
        return

    existing_rows = {
        (row.role_id, row.permission_id): row
        for row in RolePermission.objects.filter(
            role_id__in=role_ids,
            permission_id__in=permission_ids,
        )
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
    dependencies = [("rbac", "0211_repair_purchase_note_workflow_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
