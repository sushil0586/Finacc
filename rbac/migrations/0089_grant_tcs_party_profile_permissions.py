from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "tcs_party_profile_role_grants_2026_04_29"
TARGET_ROLE_CODES = (
    "entity.super_admin",
    "entity.admin",
    "admin",
    "compliance_user",
)

PARTY_PROFILE_PERMISSION_SPECS = (
    ("tcs.partyprofile.view", "View TCS Party Profile"),
    ("tcs.partyprofile.create", "Create TCS Party Profile"),
    ("tcs.partyprofile.edit", "Edit TCS Party Profile"),
    ("tcs.partyprofile.update", "Update TCS Party Profile"),
    ("tcs.partyprofile.delete", "Delete TCS Party Profile"),
)


def _permission_parts(code: str):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = "_".join(parts[1:-1])
    return module, resource, action


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, label in PARTY_PROFILE_PERMISSION_SPECS:
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
        Role.objects.filter(code__in=TARGET_ROLE_CODES, isactive=True).values_list("id", flat=True)
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
        ("rbac", "0088_grant_tcs_config_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
