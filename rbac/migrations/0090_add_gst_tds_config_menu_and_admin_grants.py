from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "gst_tds_config_menu_and_admin_grants_2026_04_30"
CATALOG_VERSION = "gst_tds_config_menu_2026_04_30"

TARGET_ROLE_CODES = (
    "entity.super_admin",
    "entity.admin",
    "admin",
)

MENU_SPEC = {
    "code": "compliance.gstdsconfig",
    "name": "GST-TDS Config",
    "route_path": "gstdsconfig",
    "route_name": "gstdsconfig",
    "icon": "sliders2",
    "sort_order": 36,
    "parent_code": "compliance",
}

PERMISSION_SPECS = (
    ("tcs.config.view", "View TCS Config"),
    ("tcs.config.create", "Create TCS Config"),
    ("tcs.config.edit", "Edit TCS Config"),
    ("tcs.config.update", "Update TCS Config"),
    ("tcs.config.delete", "Delete TCS Config"),
    ("tcs.partyprofile.view", "View TCS Party Profile"),
    ("tcs.partyprofile.create", "Create TCS Party Profile"),
    ("tcs.partyprofile.edit", "Edit TCS Party Profile"),
    ("tcs.partyprofile.update", "Update TCS Party Profile"),
    ("tcs.partyprofile.delete", "Delete TCS Party Profile"),
    ("gst.tds.config.view", "View GST-TDS Config"),
    ("gst.tds.config.create", "Create GST-TDS Config"),
    ("gst.tds.config.edit", "Edit GST-TDS Config"),
    ("gst.tds.config.update", "Update GST-TDS Config"),
    ("gst.tds.config.delete", "Delete GST-TDS Config"),
)


def _permission_parts(code: str):
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = "_".join(parts[1:-1])
    return module, resource, action


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids_by_code = {}
    for code, label in PERMISSION_SPECS:
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
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_ids_by_code[code] = permission.id

    parent = Menu.objects.filter(code=MENU_SPEC["parent_code"], isactive=True).first()
    if parent is not None:
        menu, _ = Menu.objects.update_or_create(
            code=MENU_SPEC["code"],
            defaults={
                "parent_id": parent.id,
                "name": MENU_SPEC["name"],
                "menu_type": "screen",
                "route_path": MENU_SPEC["route_path"],
                "route_name": MENU_SPEC["route_name"],
                "icon": MENU_SPEC["icon"],
                "sort_order": MENU_SPEC["sort_order"],
                "is_system_menu": True,
                "isactive": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": MENU_SPEC["code"],
                    "permission_code": "gst.tds.config.view",
                },
            },
        )
        MenuPermission.objects.get_or_create(
            menu_id=menu.id,
            permission_id=permission_ids_by_code["gst.tds.config.view"],
        )

    grant_permission_ids = list(permission_ids_by_code.values())
    role_ids = list(Role.objects.filter(code__in=TARGET_ROLE_CODES, isactive=True).values_list("id", flat=True))
    if not role_ids or not grant_permission_ids:
        return

    existing_rows = {
        (row.role_id, row.permission_id): row
        for row in RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=grant_permission_ids)
    }

    inserts = []
    for role_id in role_ids:
        for permission_id in grant_permission_ids:
            row = existing_rows.get((role_id, permission_id))
            if row is None:
                inserts.append(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission_id,
                        effect=ROLE_PERMISSION_ALLOW,
                        metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
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
                metadata["catalog_version"] = CATALOG_VERSION
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
        ("rbac", "0089_grant_tcs_party_profile_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
