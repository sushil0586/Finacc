from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "core_module_permissions_restore_2026_04_18"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

ACTION_LABELS = {
    "view": "View",
    "create": "Create",
    "update": "Update",
    "edit": "Edit",
    "delete": "Delete",
    "print": "Print",
    "confirm": "Confirm",
    "post": "Post",
    "unpost": "Unpost",
    "cancel": "Cancel",
    "submit": "Submit",
    "submit_approval": "Submit For Approval",
    "approve": "Approve",
    "reject": "Reject",
    "export": "Export",
    "manage": "Manage",
    "ensure": "Ensure",
    "fetch": "Fetch",
    "generate_irn": "Generate IRN",
    "generate_eway": "Generate EWay",
    "cancel_irn": "Cancel IRN",
    "cancel_eway": "Cancel EWay",
    "update_eway": "Update EWay",
}

DOCUMENT_ACTIONS = ("view", "create", "update", "edit", "delete", "print", "confirm", "post", "unpost", "cancel")
VOUCHER_ACTIONS = ("view", "create", "update", "edit", "delete", "print", "confirm", "post", "unpost", "cancel")
APPROVAL_ACTIONS = ("submit", "submit_approval", "approve", "reject")

DOCUMENT_FAMILIES = (
    ("sales.invoice", "Sales Invoice"),
    ("sales.credit_note", "Sales Credit Note"),
    ("sales.debit_note", "Sales Debit Note"),
    ("purchase.invoice", "Purchase Invoice"),
    ("purchase.credit_note", "Purchase Credit Note"),
    ("purchase.debit_note", "Purchase Debit Note"),
)

VOUCHER_FAMILIES = (
    ("voucher.payment", "Payment Voucher"),
    ("voucher.receipt", "Receipt Voucher"),
    ("voucher.cash", "Cash Voucher"),
    ("voucher.bank", "Bank Voucher"),
    ("voucher.journal", "Journal Voucher"),
)

LEGACY_VOUCHER_FAMILIES = (
    ("payment.voucher", "Payment Voucher"),
    ("receipt.voucher", "Receipt Voucher"),
)

FIXED_PERMISSION_SPECS = (
    ("sales.settings.view", "View Sales Settings"),
    ("sales.settings.update", "Update Sales Settings"),
    ("sales.compliance.view", "View Sales Compliance"),
    ("sales.compliance.ensure", "Ensure Sales Compliance"),
    ("sales.compliance.fetch", "Fetch Sales Compliance"),
    ("sales.compliance.generate_irn", "Generate Sales IRN"),
    ("sales.compliance.generate_eway", "Generate Sales EWay"),
    ("sales.compliance.cancel_irn", "Cancel Sales IRN"),
    ("sales.compliance.cancel_eway", "Cancel Sales EWay"),
    ("sales.compliance.update_eway", "Update Sales EWay"),
    ("purchase.statutory.view", "View Purchase Statutory"),
    ("purchase.statutory.manage", "Manage Purchase Statutory"),
    ("purchase.statutory.approve", "Approve Purchase Statutory"),
    ("reports.payables.view", "View Payables Reports"),
    ("reports.purchasebook.view", "View Purchase Book"),
    ("reports.sales_register.view", "View Sales Register"),
    ("reports.sales_register.export", "Export Sales Register"),
    ("reports.accountspayableaging.view", "View Accounts Payable Aging"),
    ("reports.vendoroutstanding.view", "View Vendor Outstanding"),
    ("reports.vendorledgerstatement.view", "View Vendor Ledger Statement"),
    ("reports.vendorsettlementhistory.view", "View Vendor Settlement History"),
    ("reports.vendornoteregister.view", "View Vendor Note Register"),
    ("reports.vendorbalanceexceptions.view", "View Vendor Balance Exceptions"),
    ("reports.payablesclosepack.view", "View Payables Close Pack"),
    ("reports.apglreconciliation.view", "View AP GL Reconciliation"),
    ("reports.inventory.view", "View Inventory Reports"),
    ("reports.inventory.stock_summary.view", "View Inventory Stock Summary"),
    ("reports.inventory.location_stock.view", "View Inventory Location Stock"),
    ("reports.inventory.stock_ledger.view", "View Inventory Stock Ledger"),
    ("reports.inventory.stock_aging.view", "View Inventory Stock Aging"),
    ("reports.inventory.non_moving_stock.view", "View Inventory Non Moving Stock"),
    ("reports.inventory.reorder_status.view", "View Inventory Reorder Status"),
    ("reports.inventory.stock_movement.view", "View Inventory Stock Movement"),
    ("reports.inventory.stock_day_book.view", "View Inventory Stock Day Book"),
    ("reports.inventory.stock_book_summary.view", "View Inventory Stock Book Summary"),
    ("reports.inventory.stock_book_detail.view", "View Inventory Stock Book Detail"),
)


def _permission_parts(code: str):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = "_".join(parts[1:-1])
    return module, resource, action


def _label_for_code(code: str) -> str:
    module, resource, action = _permission_parts(code)
    resource_label = resource.replace("_", " ").title()
    action_label = ACTION_LABELS.get(action, action.replace("_", " ").title())
    return f"{action_label} {resource_label}".strip()


def _upsert_permission(Permission, code: str, label: str) -> int:
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
            "metadata": {
                "seed": SEED_TAG,
            },
            "isactive": True,
        },
    )
    return permission.id


def _reconcile_role_permissions(RolePermission, roles, permission_ids):
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


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []

    for prefix, label in DOCUMENT_FAMILIES:
        for action in DOCUMENT_ACTIONS:
            permission_ids.append(_upsert_permission(Permission, f"{prefix}.{action}", f"{ACTION_LABELS[action]} {label}"))

    for prefix, label in VOUCHER_FAMILIES:
        for action in VOUCHER_ACTIONS:
            permission_ids.append(_upsert_permission(Permission, f"{prefix}.{action}", f"{ACTION_LABELS[action]} {label}"))

    for prefix, label in LEGACY_VOUCHER_FAMILIES:
        for action in VOUCHER_ACTIONS + APPROVAL_ACTIONS:
            permission_ids.append(_upsert_permission(Permission, f"{prefix}.{action}", f"{ACTION_LABELS[action]} {label}"))

    for action in VOUCHER_ACTIONS + APPROVAL_ACTIONS:
        permission_ids.append(_upsert_permission(Permission, f"voucher.payment.{action}", f"{ACTION_LABELS[action]} Payment Voucher"))
        permission_ids.append(_upsert_permission(Permission, f"voucher.receipt.{action}", f"{ACTION_LABELS[action]} Receipt Voucher"))

    for code, label in FIXED_PERMISSION_SPECS:
        permission_ids.append(_upsert_permission(Permission, code, label))

    roles = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).only("id"))
    if roles and permission_ids:
        _reconcile_role_permissions(RolePermission, roles, sorted(set(permission_ids)))


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0065_restore_document_workflow_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
