from django.db import migrations


CATALOG_VERSION = "payables_report_menu_group_2026_03_16"
MENU_RELATION_VISIBILITY = "visibility"

PARENT_MENU = {
    "code": "reports.payables",
    "name": "Payables Reports",
    "menu_type": "screen",
    "route_path": "/reports/payables",
    "route_name": "reports-payables",
    "icon": "wallet-minimal",
    "sort_order": 13,
}

PAYABLE_MENU_SPECS = (
    {
        "code": "reports.vendoroutstanding",
        "report_code": "vendor_outstanding",
        "name": "Vendor Outstanding Report",
        "route_path": "/reports/payables/vendor_outstanding",
        "route_name": "vendoroutstanding",
        "icon": "wallet-minimal",
        "sort_order": 1,
        "permission_code": "reports.vendoroutstanding.view",
    },
    {
        "code": "reports.accountspayableaging",
        "report_code": "ap_aging",
        "name": "AP Aging Report",
        "route_path": "/reports/payables/ap_aging",
        "route_name": "accountspayableaging",
        "icon": "timer",
        "sort_order": 2,
        "permission_code": "reports.accountspayableaging.view",
    },
    {
        "code": "reports.payables.payables_dashboard_summary",
        "report_code": "payables_dashboard_summary",
        "name": "Payables Dashboard Summary",
        "route_path": "/reports/payables/payables_dashboard_summary",
        "route_name": "reports-payables-payables-dashboard-summary",
        "icon": "layout-dashboard",
        "sort_order": 3,
        "permission_code": "reports.vendoroutstanding.view",
    },
    {
        "code": "reports.payables.purchase_register",
        "report_code": "purchase_register",
        "name": "Purchase Register",
        "route_path": "/reports/payables/purchase_register",
        "route_name": "reports-payables-purchase-register",
        "icon": "book-copy",
        "sort_order": 4,
        "permission_code": "reports.purchasebook.view",
    },
    {
        "code": "reports.vendorledgerstatement",
        "report_code": "vendor_ledger_statement",
        "name": "Vendor Ledger Statement",
        "route_path": "/reports/payables/vendor_ledger_statement",
        "route_name": "vendorledgerstatement",
        "icon": "book-text",
        "sort_order": 5,
        "permission_code": "reports.vendorledgerstatement.view",
    },
    {
        "code": "reports.vendorsettlementhistory",
        "report_code": "vendor_settlement_history",
        "name": "Vendor Settlement History",
        "route_path": "/reports/payables/vendor_settlement_history",
        "route_name": "vendorsettlementhistory",
        "icon": "hand-coins",
        "sort_order": 6,
        "permission_code": "reports.vendorsettlementhistory.view",
    },
    {
        "code": "reports.vendornoteregister",
        "report_code": "vendor_note_register",
        "name": "Vendor Debit/Credit Note Register",
        "route_path": "/reports/payables/vendor_note_register",
        "route_name": "vendornoteregister",
        "icon": "receipt-text",
        "sort_order": 7,
        "permission_code": "reports.vendornoteregister.view",
    },
    {
        "code": "reports.vendorbalanceexceptions",
        "report_code": "vendor_balance_exceptions",
        "name": "Vendor Balance Exception Report",
        "route_path": "/reports/payables/vendor_balance_exceptions",
        "route_name": "vendorbalanceexceptions",
        "icon": "alert-triangle",
        "sort_order": 8,
        "permission_code": "reports.vendorbalanceexceptions.view",
    },
    {
        "code": "reports.apglreconciliation",
        "report_code": "ap_gl_reconciliation",
        "name": "AP to GL Reconciliation Report",
        "route_path": "/reports/payables/ap_gl_reconciliation",
        "route_name": "apglreconciliation",
        "icon": "scale",
        "sort_order": 9,
        "permission_code": "reports.apglreconciliation.view",
    },
    {
        "code": "reports.payables.payables_close_validation",
        "report_code": "payables_close_validation",
        "name": "Payables Close Validation",
        "route_path": "/reports/payables/payables_close_validation",
        "route_name": "reports-payables-payables-close-validation",
        "icon": "shield-check",
        "sort_order": 10,
        "permission_code": "reports.apglreconciliation.view",
    },
    {
        "code": "reports.payables.payables_close_readiness_summary",
        "report_code": "payables_close_readiness_summary",
        "name": "Payables Close Readiness Summary",
        "route_path": "/reports/payables/payables_close_readiness_summary",
        "route_name": "reports-payables-payables-close-readiness-summary",
        "icon": "clipboard-check",
        "sort_order": 11,
        "permission_code": "reports.apglreconciliation.view",
    },
    {
        "code": "reports.payablesclosepack",
        "report_code": "payables_close_pack",
        "name": "Payables Close Pack",
        "route_path": "/reports/payables/payables_close_pack",
        "route_name": "payablesclosepack",
        "icon": "briefcase-business",
        "sort_order": 12,
        "permission_code": "reports.payablesclosepack.view",
    },
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    financial_parent = Menu.objects.filter(code="reports.financial").first() or Menu.objects.filter(code="reports").first()
    parent_menu, _ = Menu.objects.update_or_create(
        code=PARENT_MENU["code"],
        defaults={
            "parent_id": financial_parent.id if financial_parent else None,
            "name": PARENT_MENU["name"],
            "menu_type": PARENT_MENU["menu_type"],
            "route_path": PARENT_MENU["route_path"],
            "route_name": PARENT_MENU["route_name"],
            "icon": PARENT_MENU["icon"],
            "sort_order": PARENT_MENU["sort_order"],
            "is_system_menu": True,
            "metadata": {
                "seed": "payables_report_menu_group",
                "catalog_version": CATALOG_VERSION,
                "menu_code": PARENT_MENU["code"],
                "is_payables_parent": True,
            },
            "isactive": True,
        },
    )

    for spec in PAYABLE_MENU_SPECS:
        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": "payables_report_menu_group",
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                    "report_code": spec["report_code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )
        permission = Permission.objects.filter(code=spec["permission_code"], isactive=True).first()
        if permission:
            MenuPermission.objects.update_or_create(
                menu_id=menu.id,
                permission_id=permission.id,
                relation_type=MENU_RELATION_VISIBILITY,
                defaults={"isactive": True},
            )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0026_add_payables_audit_report_menus")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
