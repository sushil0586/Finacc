from django.db import migrations


PAYABLES_ROUTE_FIXES = {
    "reports.vendorsettlementhistory": {
        "route_path": "/reports/payables/vendor_settlement_history",
        "route_name": "reports-payables-vendor-settlement-history",
    },
    "reports.vendornoteregister": {
        "route_path": "/reports/payables/vendor_note_register",
        "route_name": "reports-payables-vendor-note-register",
    },
    "reports.apglreconciliation": {
        "route_path": "/reports/payables/ap_gl_reconciliation",
        "route_name": "reports-payables-ap-gl-reconciliation",
    },
    "reports.vendorbalanceexceptions": {
        "route_path": "/reports/payables/vendor_balance_exceptions",
        "route_name": "reports-payables-vendor-balance-exceptions",
    },
    "admin.role_list": {
        "route_path": "/rbacmanagement?tab=roles",
        "route_name": "rbacmanagement-tab-roles",
    },
}


RETIRED_MENU_CODES = {
    "reports.interestcalculatorindividualreport",
}


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    for code, route in PAYABLES_ROUTE_FIXES.items():
        for menu in Menu.objects.filter(code=code):
            metadata = dict(menu.metadata or {})
            metadata["canonical_route"] = route["route_path"]
            metadata["route_repair"] = "payables_operational_reports_2026_09_23"
            menu.route_path = route["route_path"]
            menu.route_name = route["route_name"]
            menu.metadata = metadata
            menu.isactive = True
            menu.save(update_fields=["route_path", "route_name", "metadata", "isactive", "updated_at"])

    retired_ids = []
    for menu in Menu.objects.filter(code__in=RETIRED_MENU_CODES):
        metadata = dict(menu.metadata or {})
        metadata["retired_reason"] = "frontend_route_removed"
        metadata["route_repair"] = "payables_operational_reports_2026_09_23"
        menu.isactive = False
        menu.metadata = metadata
        menu.save(update_fields=["isactive", "metadata", "updated_at"])
        retired_ids.append(menu.id)

    if retired_ids:
        MenuPermission.objects.filter(menu_id__in=retired_ids).update(isactive=False)


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0179_resync_payroll_finance_period_support_permission"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
