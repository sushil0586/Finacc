from django.db import migrations


SEED_TAG = "retire_legacy_tds_report_menu_2026_10_02"

RETIRED_MENU_CODES = (
    "reports.tdsreport",
    "reports.compliance.tdsreport",
)

RETIRED_ROUTE_PATHS = (
    "/tdsreport",
    "tdsreport",
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    retired_menus = Menu.objects.filter(code__in=RETIRED_MENU_CODES) | Menu.objects.filter(route_path__in=RETIRED_ROUTE_PATHS)
    retired_ids = list(retired_menus.values_list("id", flat=True))
    if retired_ids:
        Menu.objects.filter(id__in=retired_ids).update(
            isactive=False,
            route_path="",
            route_name="",
            metadata={
                "seed": SEED_TAG,
                "retired_legacy_tds_report": True,
                "replacement_route": "/reports/tds",
            },
        )
        MenuPermission.objects.filter(menu_id__in=retired_ids).update(isactive=False)

    inactive_permission_ids = list(
        MenuPermission.objects.filter(
            isactive=True,
            permission__isactive=False,
        ).values_list("id", flat=True)
    )
    if inactive_permission_ids:
        MenuPermission.objects.filter(id__in=inactive_permission_ids).update(isactive=False)


def backwards(apps, schema_editor):
    # The modern catalog owns TDS through /reports/tds. Do not recreate the
    # legacy menu on reverse because it duplicates the compliance center.
    pass


class Migration(migrations.Migration):
    dependencies = [("rbac", "0214_rehome_operational_setup_menus")]

    operations = [migrations.RunPython(forwards, backwards)]
