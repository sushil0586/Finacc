from django.db import migrations


SEED_TAG = "financial_hub_ledger_summary_route_reconcile"

CANONICAL_MENU_CODE = "reports.financial_hub.ledger_summary"
CANONICAL_ROUTE_PATH = "/reports/financial/ledger-summary"
CANONICAL_ROUTE_NAME = "financial-ledger-summary"
CANONICAL_PERMISSION_CODE = "reports.financial_hub.ledger_summary.view"

LEGACY_MENU_CODE = "reports.ledgersummary"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Permission = apps.get_model("rbac", "Permission")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    canonical_menu = Menu.objects.filter(code=CANONICAL_MENU_CODE).first()
    if canonical_menu is not None:
        canonical_menu.route_path = CANONICAL_ROUTE_PATH
        canonical_menu.route_name = CANONICAL_ROUTE_NAME
        canonical_menu.isactive = True
        canonical_menu.metadata = {
            **(canonical_menu.metadata or {}),
            "seed": SEED_TAG,
            "canonical_route": CANONICAL_ROUTE_PATH,
            "legacy_aliases": ["/ledgersummary", "ledgersummary"],
        }
        canonical_menu.save(
            update_fields=["route_path", "route_name", "isactive", "metadata", "updated_at"]
        )

        permission = Permission.objects.filter(code=CANONICAL_PERMISSION_CODE).first()
        if permission is not None:
            menu_permission, created = MenuPermission.objects.get_or_create(
                menu=canonical_menu,
                permission=permission,
                relation_type="visibility",
                defaults={"isactive": True},
            )
            if not created and not menu_permission.isactive:
                menu_permission.isactive = True
                menu_permission.save(update_fields=["isactive", "updated_at"])

    legacy_menu = Menu.objects.filter(code=LEGACY_MENU_CODE).first()
    if legacy_menu is not None:
        legacy_menu.isactive = False
        legacy_menu.metadata = {
            **(legacy_menu.metadata or {}),
            "seed": SEED_TAG,
            "legacy": True,
            "replaced_by": CANONICAL_MENU_CODE,
        }
        legacy_menu.save(update_fields=["isactive", "metadata", "updated_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0109_add_financial_hub_ledger_summary_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
