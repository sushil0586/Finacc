from django.db import migrations


SEED_TAG = "rehome_operational_setup_menus_2026_10_01"

RETIRED_ADMIN_MENU_CODES = (
    "admin.organization_structure",
    "admin.manufacturing_settings",
    "admin.commerce_promotions",
)


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    retired_menus = Menu.objects.filter(code__in=RETIRED_ADMIN_MENU_CODES)
    retired_ids = list(retired_menus.values_list("id", flat=True))
    if retired_ids:
        Menu.objects.filter(id__in=retired_ids).update(
            isactive=False,
            metadata={
                "seed": SEED_TAG,
                "retired_admin_setup_alias": True,
            },
        )
        MenuPermission.objects.filter(menu_id__in=retired_ids).update(isactive=False)


def backwards(apps, schema_editor):
    # The current catalog owns the forward shape; legacy aliases are intentionally
    # not recreated on reverse to avoid duplicate navigation entries.
    pass


class Migration(migrations.Migration):
    dependencies = [("rbac", "0213_repair_manufacturing_report_menu_permission")]

    operations = [migrations.RunPython(forwards, backwards)]
