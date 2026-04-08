from django.db import migrations


EXCLUDED_MENU_ROUTES = {
    "downloadinvoices",
    "creditnote",
    "debitnote",
    "tdsvoucher",
    "stockvoucher",
    "productionvoucher",
    "bulkinsertproduct",
    "stockmanagement",
    "productionorder",
    "stockreport",
    "stockledgersummary",
    "stockledgerbook",
    "stockdaybook",
    "stockbookreport",
    "stockbooksummary",
    "stockmovementreport",
    "stockagingreport",
    "branch",
    "entityfinyear",
    "configuration",
    "setting",
    "businesssettings",
    "ledgersummary",
}

EXCLUDED_ROOT_CODES = {"masters", "statutory", "inventory"}

EXCLUDED_PERMISSION_CODES = {
    "invoice.download.view",
    "voucher.credit_note.view",
    "voucher.debit_note.view",
    "voucher.tds.view",
    "voucher.stock.view",
    "voucher.production.view",
    "inventory.product_bulk_import.view",
    "inventory.stock_management.view",
    "inventory.production_order.view",
    "reports.stock.view",
    "admin.branch.view",
    "admin.entity_finyear.view",
    "admin.configuration.view",
    "admin.business_settings.view",
    "reports.ledger_summary.view",
}

EXCLUDED_PERMISSION_PREFIXES = (
    "voucher.credit_note.",
    "voucher.debit_note.",
    "voucher.tds.",
    "voucher.stock.",
    "voucher.production.",
    "inventory.product_bulk_import.",
    "inventory.stock_management.",
    "inventory.production_order.",
    "reports.stock.",
    "admin.branch.",
    "admin.entity_finyear.",
    "admin.configuration.",
    "admin.business_settings.",
    "reports.ledger_summary.",
)

EXCLUDED_PERMISSION_MODULES = {"credit", "debit", "tds", "stock", "inventory"}


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")

    for menu in Menu.objects.filter(isactive=True):
        if menu.code in EXCLUDED_ROOT_CODES or any(menu.code.startswith(f"{root}.") for root in EXCLUDED_ROOT_CODES):
            menu.isactive = False
            menu.save(update_fields=["isactive", "updated_at"])
            continue
        if menu.route_path in EXCLUDED_MENU_ROUTES:
            menu.isactive = False
            menu.save(update_fields=["isactive", "updated_at"])

    for permission in Permission.objects.filter(isactive=True, is_system_defined=True):
        if permission.code in EXCLUDED_PERMISSION_CODES:
            permission.isactive = False
            permission.save(update_fields=["isactive", "updated_at"])
            continue
        if permission.module in EXCLUDED_PERMISSION_MODULES:
            permission.isactive = False
            permission.save(update_fields=["isactive", "updated_at"])
            continue
        if any(permission.code.startswith(prefix) for prefix in EXCLUDED_PERMISSION_PREFIXES):
            permission.isactive = False
            permission.save(update_fields=["isactive", "updated_at"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")

    Menu.objects.filter(route_path__in=EXCLUDED_MENU_ROUTES).update(isactive=True)
    for root_code in EXCLUDED_ROOT_CODES:
        Menu.objects.filter(code=root_code).update(isactive=True)
        Menu.objects.filter(code__startswith=f"{root_code}.").update(isactive=True)

    Permission.objects.filter(code__in=EXCLUDED_PERMISSION_CODES).update(isactive=True)
    for prefix in EXCLUDED_PERMISSION_PREFIXES:
        Permission.objects.filter(code__startswith=prefix).update(isactive=True)
    Permission.objects.filter(module__in=EXCLUDED_PERMISSION_MODULES).update(isactive=True)


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0038_seed_route_based_rbac_catalog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
