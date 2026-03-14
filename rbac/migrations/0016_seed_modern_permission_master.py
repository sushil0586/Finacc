from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
PERMISSION_CATALOG_VERSION = "modern_permission_master_2026_03"

PERMISSION_SPECS = [
    ("sales.invoice.view", "View Sales Invoice", "sales", "invoice", "view"),
    ("sales.invoice.create", "Create Sales Invoice", "sales", "invoice", "create"),
    ("sales.invoice.update", "Update Sales Invoice", "sales", "invoice", "update"),
    ("sales.invoice.cancel", "Cancel Sales Invoice", "sales", "invoice", "cancel"),
    ("sales.invoice.post", "Post Sales Invoice", "sales", "invoice", "post"),
    ("sales.settings.view", "View Sales Settings", "sales", "settings", "view"),
    ("sales.settings.update", "Update Sales Settings", "sales", "settings", "update"),

    ("purchase.invoice.view", "View Purchase Invoice", "purchase", "invoice", "view"),
    ("purchase.invoice.create", "Create Purchase Invoice", "purchase", "invoice", "create"),
    ("purchase.invoice.update", "Update Purchase Invoice", "purchase", "invoice", "update"),
    ("purchase.invoice.cancel", "Cancel Purchase Invoice", "purchase", "invoice", "cancel"),
    ("purchase.invoice.post", "Post Purchase Invoice", "purchase", "invoice", "post"),

    ("admin.user.view", "View Users", "admin", "user", "view"),
    ("admin.user.create", "Create Users", "admin", "user", "create"),
    ("admin.user.update", "Update Users", "admin", "user", "update"),
    ("admin.user.delete", "Delete Users", "admin", "user", "delete"),

    ("admin.role.view", "View Roles", "admin", "role", "view"),
    ("admin.role.create", "Create Roles", "admin", "role", "create"),
    ("admin.role.update", "Update Roles", "admin", "role", "update"),
    ("admin.role.delete", "Delete Roles", "admin", "role", "delete"),

    ("admin.branch.view", "View Branches", "admin", "branch", "view"),
    ("admin.branch.create", "Create Branches", "admin", "branch", "create"),
    ("admin.branch.update", "Update Branches", "admin", "branch", "update"),
    ("admin.branch.delete", "Delete Branches", "admin", "branch", "delete"),

    ("admin.finyear.view", "View Financial Years", "admin", "finyear", "view"),
    ("admin.finyear.create", "Create Financial Years", "admin", "finyear", "create"),
    ("admin.finyear.update", "Update Financial Years", "admin", "finyear", "update"),
    ("admin.finyear.delete", "Delete Financial Years", "admin", "finyear", "delete"),

    ("admin.configuration.view", "View Configuration", "admin", "configuration", "view"),
    ("admin.configuration.update", "Update Configuration", "admin", "configuration", "update"),

    ("tcs.config.view", "View TCS Config", "tcs", "config", "view"),
    ("tcs.config.update", "Update TCS Config", "tcs", "config", "update"),
    ("tcs.section.view", "View TCS Sections", "tcs", "section", "view"),
    ("tcs.section.create", "Create TCS Sections", "tcs", "section", "create"),
    ("tcs.section.update", "Update TCS Sections", "tcs", "section", "update"),
    ("tcs.section.delete", "Delete TCS Sections", "tcs", "section", "delete"),
    ("tcs.rule.view", "View TCS Rules", "tcs", "rule", "view"),
    ("tcs.rule.create", "Create TCS Rules", "tcs", "rule", "create"),
    ("tcs.rule.update", "Update TCS Rules", "tcs", "rule", "update"),
    ("tcs.rule.delete", "Delete TCS Rules", "tcs", "rule", "delete"),
    ("tcs.party_profile.view", "View TCS Party Profiles", "tcs", "party_profile", "view"),
    ("tcs.party_profile.create", "Create TCS Party Profiles", "tcs", "party_profile", "create"),
    ("tcs.party_profile.update", "Update TCS Party Profiles", "tcs", "party_profile", "update"),
    ("tcs.party_profile.delete", "Delete TCS Party Profiles", "tcs", "party_profile", "delete"),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, module, resource, action in PERMISSION_SPECS:
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
                "metadata": {
                    "seed": "modern_permission_master",
                    "catalog_version": PERMISSION_CATALOG_VERSION,
                },
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "modern_permission_master", "catalog_version": PERMISSION_CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [row[0] for row in PERMISSION_SPECS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0015_modernize_rbac_and_remove_legacy"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
