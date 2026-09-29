from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "shared_voucher_workflow_repair_2026_09_29"

ROLE_CODES = (
    "entity.super_admin",
    "admin",
    "entity.admin",
    "accounts_manager",
    "treasury_user",
)

VOUCHER_PERMISSION_SPECS = (
    ("voucher.cash.view", "View Cash Voucher"),
    ("voucher.cash.create", "Create Cash Voucher"),
    ("voucher.cash.update", "Update Cash Voucher"),
    ("voucher.cash.edit", "Edit Cash Voucher"),
    ("voucher.cash.delete", "Delete Cash Voucher"),
    ("voucher.cash.print", "Print Cash Voucher"),
    ("voucher.cash.confirm", "Confirm Cash Voucher"),
    ("voucher.cash.post", "Post Cash Voucher"),
    ("voucher.cash.unpost", "Unpost Cash Voucher"),
    ("voucher.cash.cancel", "Cancel Cash Voucher"),
    ("voucher.bank.view", "View Bank Voucher"),
    ("voucher.bank.create", "Create Bank Voucher"),
    ("voucher.bank.update", "Update Bank Voucher"),
    ("voucher.bank.edit", "Edit Bank Voucher"),
    ("voucher.bank.delete", "Delete Bank Voucher"),
    ("voucher.bank.print", "Print Bank Voucher"),
    ("voucher.bank.confirm", "Confirm Bank Voucher"),
    ("voucher.bank.post", "Post Bank Voucher"),
    ("voucher.bank.unpost", "Unpost Bank Voucher"),
    ("voucher.bank.cancel", "Cancel Bank Voucher"),
    ("voucher.journal.view", "View Journal Voucher"),
    ("voucher.journal.create", "Create Journal Voucher"),
    ("voucher.journal.update", "Update Journal Voucher"),
    ("voucher.journal.edit", "Edit Journal Voucher"),
    ("voucher.journal.delete", "Delete Journal Voucher"),
    ("voucher.journal.print", "Print Journal Voucher"),
    ("voucher.journal.confirm", "Confirm Journal Voucher"),
    ("voucher.journal.post", "Post Journal Voucher"),
    ("voucher.journal.unpost", "Unpost Journal Voucher"),
    ("voucher.journal.cancel", "Cancel Journal Voucher"),
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
    for code, label in VOUCHER_PERMISSION_SPECS:
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
        Role.objects.filter(code__in=ROLE_CODES, isactive=True)
        .values_list("id", flat=True)
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
    dependencies = [("rbac", "0203_repair_purchase_invoice_workflow_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
