from django.db import migrations


CATALOG_VERSION = "report_menu_hierarchy_live_fix_2026_05_08"


TOP_LEVEL_GROUP_UPDATES = {
    "reports.financial_hub.receivables_hub": {
        "parent_code": "reports",
        "name": "Receivables Hub",
        "route_path": "/reports/receivables",
        "route_name": "receivables-hub",
        "sort_order": 2,
        "metadata": {"canonical_section": "reports.receivables_hub"},
    },
}


ROOT_REPORT_REPARENTING = {
    "reports.ledgerbook": "reports.financial_hub",
    "reports.ledgersummary": "reports.financial_hub",
    "reports.cashbooksummary": "reports.financial_hub",
    "reports.tradingaccountstatement": "reports.financial_hub",
    "reports.interestcalculatorindividualreport": "reports.financial_hub",

    "reports.vendoroutstanding": "reports.payables",
    "reports.accountspayableaging": "reports.payables",
    "reports.vendorledgerstatement": "reports.payables",
    "reports.payablesclosepack": "reports.payables",
    "reports.vendorsettlementhistory": "reports.payables",
    "reports.vendornoteregister": "reports.payables",
    "reports.apglreconciliation": "reports.payables",
    "reports.vendorbalanceexceptions": "reports.payables",

    "reports.gstreport": "reports.compliance",
    "reports.gstr1report": "reports.compliance",
    "reports.gstr3breport": "reports.compliance",
    "reports.gstr9report": "reports.compliance",
    "reports.tdsreport": "reports.compliance",
    "reports.tcsledgerreport": "reports.compliance",
    "reports.tcsfilingpack": "reports.compliance",

    "reports.stockledgersummary": "reports.inventory",
    "reports.stockledgerbook": "reports.inventory",
    "reports.stockdaybook": "reports.inventory",
    "reports.stockbookreport": "reports.inventory",
    "reports.stockbooksummary": "reports.inventory",
    "reports.stockmovementreport": "reports.inventory",
    "reports.stockagingreport": "reports.inventory",

    "reports.fixed-asset-register": "reports.assets",
    "reports.depreciation-schedule": "reports.assets",
    "reports.asset-events": "reports.assets",
    "reports.asset-history": "reports.assets",
}


DEACTIVATE_LEGACY_DIRECT_REPORTS = {
    "reports.trailbalance": "reports.financial_hub.trial_balance",
    "reports.daybook": "reports.financial_hub.daybook",
    "reports.salebook": "reports.financial_hub.receivables_hub.sales_register",
    "reports.purchasebook": "reports.payables.purchase_register",
    "reports.cashbook": "reports.financial_hub.cashbook",
    "reports.balancesheet": "reports.financial_hub.balance_sheet",
    "reports.incomeexpenditurereport": "reports.financial_hub.profit_loss",
    "reports.outstandingreport": "reports.financial_hub.receivables_hub.customer_outstanding",
    "reports.accountsreceivableaging": "reports.financial_hub.receivables_hub.receivable_aging",
}


def _merge_metadata(menu, extra):
    metadata = dict(menu.metadata or {})
    metadata.update(extra)
    return metadata


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")

    for code, config in TOP_LEVEL_GROUP_UPDATES.items():
        menu = Menu.objects.filter(code=code).first()
        parent = Menu.objects.filter(code=config["parent_code"]).first()
        if menu is None or parent is None:
            continue
        menu.parent_id = parent.id
        menu.name = config["name"]
        menu.route_path = config["route_path"]
        menu.route_name = config["route_name"]
        menu.sort_order = config["sort_order"]
        menu.isactive = True
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_menu_hierarchy_live_fix",
                "catalog_version": CATALOG_VERSION,
                **config["metadata"],
            },
        )
        menu.save(
            update_fields=[
                "parent_id",
                "name",
                "route_path",
                "route_name",
                "sort_order",
                "isactive",
                "metadata",
                "updated_at",
            ]
        )

    for code, parent_code in ROOT_REPORT_REPARENTING.items():
        menu = Menu.objects.filter(code=code).first()
        parent = Menu.objects.filter(code=parent_code).first()
        if menu is None or parent is None:
            continue
        menu.parent_id = parent.id
        menu.isactive = True
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_menu_hierarchy_live_fix",
                "catalog_version": CATALOG_VERSION,
                "canonical_parent": parent_code,
            },
        )
        menu.save(update_fields=["parent_id", "isactive", "metadata", "updated_at"])

    for legacy_code, replacement_code in DEACTIVATE_LEGACY_DIRECT_REPORTS.items():
        menu = Menu.objects.filter(code=legacy_code).first()
        if menu is None:
            continue
        menu.isactive = False
        menu.metadata = _merge_metadata(
            menu,
            {
                "seed": "report_menu_hierarchy_live_fix",
                "catalog_version": CATALOG_VERSION,
                "legacy": True,
                "replaced_by": replacement_code,
            },
        )
        menu.save(update_fields=["isactive", "metadata", "updated_at"])


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0100_normalize_report_section_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
