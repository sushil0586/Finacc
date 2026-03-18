from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "frontend_permission_catalog_2026_03"

PAGE_KEYS = [
    ("cash", "Cash"),
    ("bank", "Bank"),
    ("journal", "Journal"),
]

CANONICAL_ACTIONS = [
    "create",
    "edit",
    "update",
    "submit",
    "submit_approval",
    "approve",
    "reject",
    "post",
    "confirm",
    "unpost",
    "cancel",
    "delete",
]


def _canonical_specs():
    specs = []
    for key, title in PAGE_KEYS:
        resource = f"{key}voucher"
        for action in CANONICAL_ACTIONS:
            action_title = "Submit For Approval" if action == "submit_approval" else action.replace("_", " ").title()
            name = f"{action_title} {title} Voucher"
            specs.append(
                (
                    f"voucher.{resource}.{action}",
                    name,
                    "voucher",
                    resource,
                    action,
                )
            )
    return specs


def _alias_specs():
    aliases = []
    for key, title in PAGE_KEYS:
        canonical_prefix = f"voucher.{key}voucher"
        for action in CANONICAL_ACTIONS:
            action_title = "Submit For Approval" if action == "submit_approval" else action.replace("_", " ").title()
            aliases.append(
                (
                    f"{key}.voucher.{action}",
                    f"Alias {action_title} {title} Voucher",
                    f"{canonical_prefix}.{action}",
                )
            )

        aliases.append((f"{key}voucher.create", f"Alias Create {title} Voucher", f"{canonical_prefix}.create"))
        aliases.append((f"{key}voucher.edit", f"Alias Edit {title} Voucher", f"{canonical_prefix}.edit"))
    return aliases


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    canonical_specs = _canonical_specs()
    for code, name, module, resource, action in canonical_specs:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION, "kind": "canonical"},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    canonical_map = {code: (module, resource, action) for code, _, module, resource, action in canonical_specs}
    for code, name, alias_of in _alias_specs():
        module, resource, action = canonical_map.get(alias_of, ("alias", "permission", "alias"))
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": f"Temporary alias for {alias_of}",
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {
                    "seed": "frontend_permission_catalog",
                    "catalog_version": CATALOG_VERSION,
                    "kind": "alias",
                    "alias_of": alias_of,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=["entity.super_admin", "admin"], isactive=True).values_list("id", flat=True))
    existing_pairs = set(RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id"))
    inserts = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [row[0] for row in _canonical_specs()] + [row[0] for row in _alias_specs()]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0029_add_cash_bank_journal_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
