from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "financial_control_action_permissions"
CATALOG_VERSION = "financial_control_action_permissions_2026_09_10"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")

PERMISSIONS = (
    ("reports.financial_hub.controls_phase_one.update_policy", "Update Opening Policy", "controls_phase_one", "update_policy"),
    ("reports.financial_hub.controls_phase_one.generate_opening", "Generate Opening Balances", "controls_phase_one", "generate_opening"),
    ("reports.financial_hub.controls_phase_one.rollback_opening", "Rollback Opening Balances", "controls_phase_one", "rollback_opening"),
    ("reports.financial_hub.posting_setup.apply", "Apply Posting Setup", "posting_setup", "apply"),
    ("reports.financial_hub.year_end_close.execute", "Execute Year-End Close", "year_end_close", "execute"),
    ("reports.financial_hub.year_end_close.rollback", "Rollback Year-End Close", "year_end_close", "rollback"),
)


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, resource, action in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": "reports",
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    role_ids = list(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    existing = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    RolePermission.objects.bulk_create(
        [
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in role_ids
            for permission_id in permission_ids
            if (role_id, permission_id) not in existing
        ]
    )


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission_ids = list(Permission.objects.filter(code__in=[row[0] for row in PERMISSIONS]).values_list("id", flat=True))
    RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0143_add_batch_data_access_policy_type")]

    operations = [migrations.RunPython(forwards, backwards)]
