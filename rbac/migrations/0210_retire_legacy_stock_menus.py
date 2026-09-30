from django.db import migrations


SEED_TAG = "retire_legacy_stock_pages_2026_09_30"

RETIRED_MENU_CODES = (
    "inventory.stockmanagement",
    "inventory.productionorder",
    "inventory.bulkinsertproduct",
)

RETIRED_ROUTE_PATHS = (
    "/stockmanagement",
    "stockmanagement",
    "/bulkinsertproduct",
    "bulkinsertproduct",
    "/productionorder",
    "productionorder",
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
                "retired_legacy_stock_page": True,
            },
        )
        MenuPermission.objects.filter(menu_id__in=retired_ids).update(isactive=False)

    Menu.objects.filter(code="reports.inventory.production_order").update(
        route_path="/manufacturing-work-order-entry",
        route_name="manufacturing-work-order-entry",
        isactive=True,
        metadata={
            "seed": SEED_TAG,
            "canonical_route": "/manufacturing-work-order-entry",
            "retired_legacy_route": "/productionorder",
        },
    )

    Menu.objects.filter(route_path__in=("/productionorder", "productionorder")).exclude(code="reports.inventory.production_order").update(
        isactive=False,
        route_path="",
        route_name="",
        metadata={
            "seed": SEED_TAG,
            "retired_legacy_stock_page": True,
            "replacement_route": "/manufacturing-work-order-entry",
        },
    )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")

    Menu.objects.filter(code="reports.inventory.production_order").update(
        route_path="/productionorder",
        route_name="productionorder",
        isactive=True,
    )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0209_repair_inventory_ops_workflow_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
