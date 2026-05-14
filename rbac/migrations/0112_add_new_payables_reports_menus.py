from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
SEED_TAG = "payables_new_reports_menu"
CATALOG_VERSION = "payables_new_reports_menu_2026_05_13"


REPORT_SPECS = (
    {
        "menu_code": "reports.payables.ap_payment_forecast",
        "name": "AP Payment Forecast",
        "route_path": "/reports/payables/ap_payment_forecast",
        "route_name": "reports-payables-ap-payment-forecast",
        "icon": "calendar-clock",
        "sort_order": 27,
        "permission_code": "reports.payables.ap_payment_forecast.view",
    },
    {
        "menu_code": "reports.payables.vendor_reconciliation_statement",
        "name": "Vendor Reconciliation Statement",
        "route_path": "/reports/payables/vendor_reconciliation_statement",
        "route_name": "reports-payables-vendor-reconciliation-statement",
        "icon": "book-check",
        "sort_order": 28,
        "permission_code": "reports.payables.vendor_reconciliation_statement.view",
    },
    {
        "menu_code": "reports.payables.grn_invoice_posting_exceptions",
        "name": "GRN Invoice Posting Exceptions",
        "route_path": "/reports/payables/grn_invoice_posting_exceptions",
        "route_name": "reports-payables-grn-invoice-posting-exceptions",
        "icon": "alert-triangle",
        "sort_order": 29,
        "permission_code": "reports.payables.grn_invoice_posting_exceptions.view",
    },
    {
        "menu_code": "reports.payables.ap_compliance_aging",
        "name": "AP Compliance Aging",
        "route_path": "/reports/payables/ap_compliance_aging",
        "route_name": "reports-payables-ap-compliance-aging",
        "icon": "shield-check",
        "sort_order": 30,
        "permission_code": "reports.payables.ap_compliance_aging.view",
    },
    {
        "menu_code": "reports.payables.duplicate_anomalous_bill_detection",
        "name": "Duplicate/Anomalous Bill Detection",
        "route_path": "/reports/payables/duplicate_anomalous_bill_detection",
        "route_name": "reports-payables-duplicate-anomalous-bill-detection",
        "icon": "file-search",
        "sort_order": 31,
        "permission_code": "reports.payables.duplicate_anomalous_bill_detection.view",
    },
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
    RolePermission = apps.get_model("rbac", "RolePermission")

    group_menu = (
        Menu.objects.filter(code="reports.payables", isactive=True).first()
        or Menu.objects.filter(code="reports.reports.payables", isactive=True).first()
    )
    if group_menu is None:
        return

    grant_role_ids = set(
        RolePermission.objects.filter(
            permission__code__in=("reports.payables.view", "reports.vendoroutstanding.view"),
            role__isactive=True,
            isactive=True,
        ).values_list("role_id", flat=True)
    )

    for spec in REPORT_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["menu_code"],
            defaults={
                "parent_id": group_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["menu_code"],
                    "route_path": spec["route_path"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        permission_id = _upsert_permission(Permission, spec["permission_code"], menu_code=spec["menu_code"])

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission_id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )

        existing_pairs = set(
            RolePermission.objects.filter(role_id__in=grant_role_ids, permission_id=permission_id).values_list("role_id", "permission_id")
        )
        rows = [
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                effect=ROLE_PERMISSION_ALLOW,
                metadata={"seed": SEED_TAG, "catalog_version": CATALOG_VERSION},
                isactive=True,
            )
            for role_id in grant_role_ids
            if (role_id, permission_id) not in existing_pairs
        ]
        if rows:
            RolePermission.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [spec["permission_code"] for spec in REPORT_SPECS]
    menu_codes = [spec["menu_code"] for spec in REPORT_SPECS]

    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids, metadata__seed=SEED_TAG).delete()
        MenuPermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()
    Menu.objects.filter(code__in=menu_codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0111_add_payables_settings_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

