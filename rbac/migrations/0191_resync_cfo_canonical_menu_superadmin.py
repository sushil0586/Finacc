from django.db import migrations


ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin")
ROLE_PERMISSION_ALLOW = "allow"
SEED_TAG = "cfo_canonical_menu_superadmin_2026_09_24"


CFO_PERMISSION_CODES = (
    "cfo.control_tower.view",
    "cfo.receivables.view",
    "cfo.payables.view",
    "cfo.cash_flow.view",
    "cfo.cash_flow.manage_adjustments",
    "cfo.month_close.view",
    "cfo.month_close.manage",
    "cfo.month_close.lock_period",
    "cfo.budget.view",
    "cfo.budget.manage",
    "cfo.budget.review_variances",
    "cfo.risk_queue.view",
    "cfo.risk_queue.review",
    "cfo.management_pack.view",
    "cfo.management_pack.publish",
    "cfo.evidence_center.view",
    "cfo.evidence_center.manage",
    "cfo.insights.view",
    "cfo.insights.review",
    "cfo.scenario_planner.view",
    "cfo.scenario_planner.manage",
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(
        Permission.objects.filter(code__in=CFO_PERMISSION_CODES, isactive=True)
        .values_list("id", flat=True)
    )
    role_ids = list(
        Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True)
        .values_list("id", flat=True)
    )
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id__in=permission_ids)
        .values_list("role_id", "permission_id")
    )
    rows = []
    for role_id in role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            rows.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG},
                    isactive=True,
                )
            )
    if rows:
        RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0190_add_cfo_scenario_planner_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
