from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "gst_tds_compliance_center_menu"
CATALOG_VERSION = "gst_tds_compliance_center_menu_2026_06_28"


MENU_SPEC = {
    "code": "reports.financial_hub.gst_tds_compliance_center",
    "name": "GST-TDS Compliance Center",
    "parent_code": "reports.financial_hub",
    "route_path": "/reports/gst-tds",
    "route_name": "reports-gst-tds-compliance-center",
    "icon": "receipt-cutoff",
    "sort_order": 13,
    "permission_code": "reports.financial_hub.gst_tds_compliance_center.view",
}

BASE_PERMISSION_CODE = "reports.financial_hub.view"
LEGACY_PERMISSION_CODES = (
    "reports.gst.view",
    "purchase.statutory.view",
    "reports.financial_hub.tds_compliance_center.view",
)


def _permission_parts(code: str) -> tuple[str, str, str]:
    parts = code.split(".")
    module = parts[0]
    action = parts[-1]
    resource = ".".join(parts[1:-1]) or module
    return module, resource.replace(".", "_"), action


def _permission_name(code: str) -> str:
    action_labels = {
        "view": "View",
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "print": "Print",
        "post": "Post",
        "unpost": "Unpost",
        "export": "Export",
        "file": "File",
        "change": "Change",
    }
    parts = code.split(".")
    action = parts[-1]
    resource = " ".join(part.replace("_", " ").replace("-", " ") for part in parts[1:-1])
    resource = resource.title() if resource else parts[0].title()
    return f"{action_labels.get(action, action.title())} {resource}".strip()


def _upsert_permission(Permission, permission_code: str, *, menu_code: str) -> int:
    module, resource, action = _permission_parts(permission_code)
    permission, _ = Permission.objects.update_or_create(
        code=permission_code,
        defaults={
            "name": _permission_name(permission_code),
            "module": module,
            "resource": resource,
            "action": action,
            "description": _permission_name(permission_code),
            "scope_type": PERMISSION_SCOPE_ENTITY,
            "is_system_defined": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": menu_code,
            },
            "isactive": True,
        },
    )
    return permission.id


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    financial_hub = Menu.objects.filter(code=MENU_SPEC["parent_code"], isactive=True).first()
    reports_parent = Menu.objects.filter(code="reports", isactive=True).first()
    if financial_hub is None:
        financial_hub = reports_parent
    if financial_hub is None:
        return

    menu, _ = Menu.objects.update_or_create(
        code=MENU_SPEC["code"],
        defaults={
            "parent_id": financial_hub.id,
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
                "menu_code": MENU_SPEC["code"],
                "route_path": MENU_SPEC["route_path"],
                "permission_code": MENU_SPEC["permission_code"],
                "legacy_permission_codes": list(LEGACY_PERMISSION_CODES),
            },
            "isactive": True,
        },
    )

    base_permission_id = _upsert_permission(Permission, BASE_PERMISSION_CODE, menu_code=MENU_SPEC["code"])
    canonical_permission_id = _upsert_permission(Permission, MENU_SPEC["permission_code"], menu_code=MENU_SPEC["code"])

    MenuPermission.objects.update_or_create(
        menu_id=menu.id,
        permission_id=canonical_permission_id,
        relation_type=MENU_RELATION_VISIBILITY,
        defaults={"isactive": True},
    )

    source_permission_codes = [
        BASE_PERMISSION_CODE,
        MENU_SPEC["permission_code"],
        *LEGACY_PERMISSION_CODES,
    ]
    source_role_ids = set()
    for code in source_permission_codes:
        source_role_ids.update(
            RolePermission.objects.filter(
                permission__code=code,
                role__isactive=True,
                isactive=True,
            ).values_list("role_id", flat=True)
        )

    if not source_role_ids:
        source_role_ids.update(
            Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True)
        )

    grant_permission_ids = [base_permission_id, canonical_permission_id]
    existing_pairs = set(
        RolePermission.objects.filter(
            role_id__in=source_role_ids,
            permission_id__in=grant_permission_ids,
        ).values_list("role_id", "permission_id")
    )

    inserts = []
    for role_id in source_role_ids:
        for permission_id in grant_permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )

    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    cleanup_permission_codes = [BASE_PERMISSION_CODE, MENU_SPEC["permission_code"]]
    cleanup_permission_ids = list(Permission.objects.filter(code__in=cleanup_permission_codes).values_list("id", flat=True))
    if cleanup_permission_ids:
        RolePermission.objects.filter(permission_id__in=cleanup_permission_ids, metadata__seed=SEED_TAG).delete()

    permission_ids = list(Permission.objects.filter(code=MENU_SPEC["permission_code"]).values_list("id", flat=True))
    if permission_ids:
        MenuPermission.objects.filter(menu__code=MENU_SPEC["code"], permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids, metadata__seed=SEED_TAG).delete()

    Menu.objects.filter(code=MENU_SPEC["code"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0130_add_tds_compliance_center_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
