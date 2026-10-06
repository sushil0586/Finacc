from django.db import migrations


SEED_TAG = "flatten_payables_receivables_report_menus_2026_10_06"

PAYABLES_FLAT_ORDER = (
    ("reports.payables.hub", 5),
    ("reports.vendoroutstanding", 10),
    ("reports.vendorledgerstatement", 20),
    ("reports.payables.ap_aging", 30),
    ("reports.payables.upcoming_payments_calendar", 40),
    ("reports.payables.ap_payment_forecast", 50),
    ("reports.payables.msme_overdue", 60),
    ("reports.payables.vendor_reconciliation_statement", 70),
    ("reports.payables.grn_invoice_posting_exceptions", 80),
    ("reports.payables.ap_compliance_aging", 90),
    ("reports.payables.duplicate_anomalous_bill_detection", 100),
    ("reports.payablesclosepack", 110),
    ("reports.vendorsettlementhistory", 120),
    ("reports.vendornoteregister", 130),
    ("reports.apglreconciliation", 140),
    ("reports.payables.purchase_register", 150),
    ("reports.vendorbalanceexceptions", 160),
    ("reports.payables.settings", 170),
)


def _merge_metadata(menu, extra):
    metadata = dict(menu.metadata or {})
    metadata.update(extra)
    return metadata


def _save_menu(menu, update_fields):
    menu.metadata = _merge_metadata(menu, {"seed": SEED_TAG})
    menu.save(update_fields=[*update_fields, "metadata", "updated_at"])


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    reports = Menu.objects.filter(code="reports").first()
    payables = Menu.objects.filter(code="reports.payables").first()
    receivables = Menu.objects.filter(code="reports.receivables").first()
    payables_hub = Menu.objects.filter(code="reports.payables.hub").first()
    receivables_hub = Menu.objects.filter(code="reports.receivables_hub").first()

    if reports and receivables:
        receivables.parent_id = reports.id
        receivables.name = "Receivables Reports"
        receivables.route_path = ""
        receivables.route_name = "reports-receivables-section"
        receivables.menu_type = "group"
        receivables.sort_order = 50
        receivables.isactive = True
        _save_menu(
            receivables,
            ["parent_id", "name", "route_path", "route_name", "menu_type", "sort_order", "isactive"],
        )

    if receivables and receivables_hub:
        receivables_hub.parent_id = receivables.id
        receivables_hub.name = "Hub Overview"
        receivables_hub.route_path = "/reports/receivables"
        receivables_hub.route_name = "reports-receivables"
        receivables_hub.menu_type = "screen"
        receivables_hub.sort_order = 5
        receivables_hub.isactive = True
        _save_menu(
            receivables_hub,
            ["parent_id", "name", "route_path", "route_name", "menu_type", "sort_order", "isactive"],
        )

    if payables and payables_hub:
        payables_hub.parent_id = payables.id
        payables_hub.name = "Hub Overview"
        payables_hub.route_path = "/reports/payables"
        payables_hub.route_name = "reports-payables"
        payables_hub.menu_type = "screen"
        payables_hub.sort_order = 5
        payables_hub.isactive = True
        _save_menu(
            payables_hub,
            ["parent_id", "name", "route_path", "route_name", "menu_type", "sort_order", "isactive"],
        )

    if payables:
        for code, sort_order in PAYABLES_FLAT_ORDER:
            menu = Menu.objects.filter(code=code).first()
            if menu is None:
                continue
            menu.parent_id = payables.id
            menu.sort_order = sort_order
            menu.isactive = True
            if code == "reports.payables.hub":
                menu.name = "Hub Overview"
                menu.route_path = "/reports/payables"
                menu.route_name = "reports-payables"
                menu.menu_type = "screen"
                _save_menu(
                    menu,
                    ["parent_id", "sort_order", "isactive", "name", "route_path", "route_name", "menu_type"],
                )
            else:
                _save_menu(menu, ["parent_id", "sort_order", "isactive"])

    sales_register = Menu.objects.filter(code="reports.receivables.sales_register").first()
    if sales_register:
        sales_register.route_path = "/reports/receivables/sales-register"
        sales_register.route_name = "reports-receivables-sales-register"
        _save_menu(sales_register, ["route_path", "route_name"])

    # Retire older duplicate top-level aliases if any live database still has
    # them alongside the canonical group/hub pair.
    duplicate_receivables = Menu.objects.filter(
        parent=reports,
        route_path="/reports/receivables",
    ).exclude(code="reports.receivables_hub")
    duplicate_ids = list(duplicate_receivables.values_list("id", flat=True))
    if duplicate_ids:
        Menu.objects.filter(id__in=duplicate_ids).update(
            isactive=False,
            metadata={
                "seed": SEED_TAG,
                "deactivated_as_duplicate_receivables_hub": True,
                "canonical_code": "reports.receivables_hub",
            },
        )
        MenuPermission.objects.filter(menu_id__in=duplicate_ids).update(isactive=False)


def backwards(apps, schema_editor):
    # Current launch catalog owns the forward menu shape.
    return


class Migration(migrations.Migration):
    dependencies = [("rbac", "0216_repair_account_bulk_master_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
