from django.db import migrations


SEED_TAG = "treasury_payment_batch_permissions_2026_09_17"
CATALOG_VERSION = "treasury_payment_batch_permissions_2026_09_17"
ROLE_PERMISSION_ALLOW = "allow"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

PERMISSIONS = (
    ("treasury.payment_batch.view", "View Treasury Payment Batches", "treasury", "payment_batch", "view"),
    ("treasury.payment_batch.create", "Create Treasury Payment Batches", "treasury", "payment_batch", "create"),
    ("treasury.payment_batch.update", "Update Treasury Payment Batches", "treasury", "payment_batch", "update"),
    ("treasury.payment_batch.validate", "Validate Treasury Payment Batches", "treasury", "payment_batch", "validate"),
    ("treasury.payment_batch.approve", "Approve Treasury Payment Batches", "treasury", "payment_batch", "approve"),
    ("treasury.payment_batch.export", "Export Treasury Payment Batches", "treasury", "payment_batch", "export"),
    ("treasury.payment_batch.mark_paid", "Mark Treasury Payment Batches Paid", "treasury", "payment_batch", "mark_paid"),
)

COPY_FROM = {
    "treasury.payment_batch.view": (
        "reports.payables.view",
        "reports.financial_hub.view",
        "reports.financial_hub.bank_reconciliation.view",
    ),
    "treasury.payment_batch.create": (
        "payments.payment_batch.create",
        "voucher.payment.create",
        "voucher.payment.view",
    ),
    "treasury.payment_batch.update": (
        "voucher.payment.update",
        "voucher.payment.post",
        "voucher.bank.view",
        "voucher.cash.view",
    ),
    "treasury.payment_batch.validate": (
        "voucher.payment.update",
        "voucher.payment.post",
    ),
    "treasury.payment_batch.approve": (
        "voucher.payment.confirm",
        "voucher.payment.approve",
        "voucher.payment.post",
    ),
    "treasury.payment_batch.export": (
        "reports.payables.export",
        "reports.financial_hub.export",
        "voucher.payment.print",
    ),
    "treasury.payment_batch.mark_paid": (
        "voucher.payment.post",
        "voucher.bank.view",
        "voucher.cash.view",
    ),
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_by_code = {}
    for code, name, module, resource, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": "entity",
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_by_code[code] = permission

    role_ids_by_permission = {code: set() for code, *_ in PERMISSIONS}
    admin_role_ids = set(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    for code in role_ids_by_permission:
        role_ids_by_permission[code].update(admin_role_ids)

    source_codes = sorted({source_code for codes in COPY_FROM.values() for source_code in codes})
    source_permission_ids_by_code = dict(
        Permission.objects.filter(code__in=source_codes, isactive=True).values_list("code", "id")
    )
    source_role_ids_by_permission_id = {}
    source_permission_ids = list(source_permission_ids_by_code.values())
    for permission_id, role_id in RolePermission.objects.filter(
        permission_id__in=source_permission_ids,
        isactive=True,
        effect=ROLE_PERMISSION_ALLOW,
    ).values_list("permission_id", "role_id"):
        source_role_ids_by_permission_id.setdefault(permission_id, set()).add(role_id)

    for target_code, source_codes_for_target in COPY_FROM.items():
        role_ids = role_ids_by_permission[target_code]
        for source_code in source_codes_for_target:
            source_permission_id = source_permission_ids_by_code.get(source_code)
            if source_permission_id:
                role_ids.update(source_role_ids_by_permission_id.get(source_permission_id, set()))

    target_permission_ids = [permission.id for permission in permission_by_code.values()]
    all_role_ids = sorted({role_id for role_ids in role_ids_by_permission.values() for role_id in role_ids})
    existing = set(
        RolePermission.objects.filter(role_id__in=all_role_ids, permission_id__in=target_permission_ids)
        .values_list("role_id", "permission_id")
    )

    inserts = []
    for code, role_ids in role_ids_by_permission.items():
        permission = permission_by_code[code]
        for role_id in role_ids:
            key = (role_id, permission.id)
            if key in existing:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission=permission,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts, batch_size=500)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = list(Permission.objects.filter(code__in=[row[0] for row in PERMISSIONS]).values_list("id", flat=True))
    RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0160_add_treasury_setup_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
