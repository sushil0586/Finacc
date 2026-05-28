from django.db import migrations


SEED_TAG = "bank_reco_menu_repoint_2026_05_24"
MENU_CODE = "reports.financial_hub.bank_reconciliation"
NEW_ROUTE_PATH = "/bank-reco"
NEW_ROUTE_NAME = "bank-reco"
LEGACY_ROUTE_PATH = "/reports/bank-reconciliation"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")

    menu = Menu.objects.filter(code=MENU_CODE).first()
    if menu is None:
        return

    metadata = dict(menu.metadata or {})
    metadata.update({
        "seed": SEED_TAG,
        "menu_code": MENU_CODE,
        "route_path": NEW_ROUTE_PATH,
        "route_name": NEW_ROUTE_NAME,
        "legacy_route_path": LEGACY_ROUTE_PATH,
    })

    menu.route_path = NEW_ROUTE_PATH
    menu.route_name = NEW_ROUTE_NAME
    menu.metadata = metadata
    menu.isactive = True
    menu.save(update_fields=["route_path", "route_name", "metadata", "isactive"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")

    menu = Menu.objects.filter(code=MENU_CODE).first()
    if menu is None:
        return

    metadata = dict(menu.metadata or {})
    metadata.update({
        "seed": SEED_TAG,
        "menu_code": MENU_CODE,
        "route_path": LEGACY_ROUTE_PATH,
        "route_name": "bank-reconciliation",
    })

    menu.route_path = LEGACY_ROUTE_PATH
    menu.route_name = "bank-reconciliation"
    menu.metadata = metadata
    menu.save(update_fields=["route_path", "route_name", "metadata"])


class Migration(migrations.Migration):
    dependencies = [("rbac", "0125_repair_msme_overdue_payables_menu_parent")]

    operations = [migrations.RunPython(forwards, backwards)]
