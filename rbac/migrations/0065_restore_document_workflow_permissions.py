from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "document_workflow_permissions_restore_2026_04_18"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

DOCUMENT_PERMISSION_SPECS = [
    ("sales.invoice", "Sales Invoice"),
    ("sales.credit_note", "Sales Credit Note"),
    ("sales.debit_note", "Sales Debit Note"),
    ("purchase.invoice", "Purchase Invoice"),
    ("purchase.credit_note", "Purchase Credit Note"),
    ("purchase.debit_note", "Purchase Debit Note"),
]

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
}

ACTION_ORDER = (
    "view",
    "create",
    "update",
    "edit",
    "delete",
    "print",
    "confirm",
    "post",
    "unpost",
    "cancel",
)


def _permission_parts(code: str):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = "_".join(parts[1:-1])
    return module, resource, action


def _permission_name(label: str, action: str) -> str:
    return f"{ACTION_LABELS[action]} {label}"


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for prefix, label in DOCUMENT_PERMISSION_SPECS:
        for action in ACTION_ORDER:
            code = f"{prefix}.{action}"
            module, resource, resolved_action = _permission_parts(code)
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "name": _permission_name(label, action),
                    "module": module,
                    "resource": resource,
                    "action": resolved_action,
                    "description": _permission_name(label, action),
                    "scope_type": PERMISSION_SCOPE_ENTITY,
                    "is_system_defined": True,
                    "metadata": {
                        "seed": SEED_TAG,
                        "document_family": prefix,
                    },
                    "isactive": True,
                },
            )
            permission_ids.append(permission.id)

    roles = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).only("id"))
    if not roles or not permission_ids:
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
    return


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0064_sync_admin_full_access"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
