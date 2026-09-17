from django.db import migrations


SEED_TAG = "gst_compliance_center_menu_2026_09_17"
CATALOG_VERSION = "gst_compliance_center_menu_2026_09_17"
MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
ADMIN_ROLE_CODES = ("entity.super_admin", "admin", "entity.admin", "report_viewer")

MENU_SPEC = {
    "code": "reports.gst_compliance_center",
    "name": "GST Compliance Center",
    "route_path": "/reports/compliance/gst-compliance-center",
    "route_name": "reports-compliance-gst-compliance-center",
    "icon": "shield-check",
    "sort_order": 0,
    "permission_code": "reports.gst_compliance_center.view",
}

COPY_FROM_PERMISSIONS = (
    "reports.gst.view",
    "reports.gstr1report.view",
    "reports.gstr3b.view",
    "reports.gstr9.view",
    "reports.gstr1_gstr3b_reconciliation.view",
    "reports.gst_exception_dashboard.view",
    "gst.reconciliation.view",
    "reports.financial_hub.gst_tds_compliance_center.view",
    "reports.financial_hub.tcs_compliance_center.view",
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    parent_menu = Menu.objects.filter(code="reports.compliance", isactive=True).first()
    if parent_menu is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": parent_menu.id,
            "name": MENU_SPEC["name"],
            "menu_type": "screen",
            "route_path": MENU_SPEC["route_path"],
            "route_name": MENU_SPEC["route_name"],
            "icon": MENU_SPEC["icon"],
            "sort_order": MENU_SPEC["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "permission_code": MENU_SPEC["permission_code"],
            },
            "isactive": True,
        },
    )

    permission, _ = Permission.objects.update_or_create(
        code=MENU_SPEC["permission_code"],
        defaults={
            "name": "Reports GST Compliance Center View",
            "module": "reports",
            "resource": "gst_compliance_center",
            "action": "view",
            "description": "View the GST Compliance Center umbrella workspace.",
            "scope_type": "entity",
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": MENU_SPEC["code"],
                "copied_from": list(COPY_FROM_PERMISSIONS),
            },
            "isactive": True,
        },
    )

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=permission.id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    role_ids = set(Role.objects.filter(code__in=ADMIN_ROLE_CODES, isactive=True).values_list("id", flat=True))
    source_permission_ids = list(
        Permission.objects.filter(code__in=COPY_FROM_PERMISSIONS, isactive=True).values_list("id", flat=True)
    )
    if source_permission_ids:
        role_ids.update(
            RolePermission.objects.filter(
                permission_id__in=source_permission_ids,
                isactive=True,
                effect=ROLE_PERMISSION_ALLOW,
            ).values_list("role_id", flat=True)
        )

    existing_role_ids = set(
        RolePermission.objects.filter(role_id__in=role_ids, permission_id=permission.id).values_list("role_id", flat=True)
    )
    inserts = [
        RolePermission(
            role_id=role_id,
            permission_id=permission.id,
            effect=ROLE_PERMISSION_ALLOW,
            metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
            isactive=True,
        )
        for role_id in sorted(role_ids)
        if role_id not in existing_role_ids
    ]
    if inserts:
        RolePermission.objects.bulk_create(inserts, batch_size=500)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = list(Permission.objects.filter(code=MENU_SPEC["permission_code"]).values_list("id", flat=True))
    menu_ids = list(Menu.objects.filter(code=MENU_SPEC["code"]).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()
    if menu_ids:
        Menu.objects.filter(id__in=menu_ids, metadata__seed=SEED_TAG).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0161_add_treasury_payment_batch_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
