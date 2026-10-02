from django.db import migrations


SEED_TAG = "manufacturing_report_menu_permission_repair_2026_10_01"
MENU_CODE = "reports.manufacturing"
NEW_PERMISSION_CODE = "reports.inventory.manufacturing_hub.view"
OLD_PERMISSION_CODE = "reports.inventory.view"
RELATION_VISIBILITY = "visibility"


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()

    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    menu = Menu.objects.filter(code=MENU_CODE).first()
    permission = Permission.objects.filter(code=NEW_PERMISSION_CODE).first()
    if not menu or not permission:
        return

    metadata = menu.metadata or {}
    metadata.update(
        {
            "seed": SEED_TAG,
            "permission_code": NEW_PERMISSION_CODE,
            "replaced_permission_code": OLD_PERMISSION_CODE,
        }
    )
    menu.metadata = metadata
    menu.isactive = True
    menu.save(update_fields=["metadata", "isactive"])

    MenuPermission.objects.filter(
        menu=menu,
        permission__code=OLD_PERMISSION_CODE,
        relation_type=RELATION_VISIBILITY,
    ).update(isactive=False)

    MenuPermission.objects.update_or_create(
        menu=menu,
        permission=permission,
        relation_type=RELATION_VISIBILITY,
        defaults={"isactive": True},
    )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    menu = Menu.objects.filter(code=MENU_CODE).first()
    old_permission = Permission.objects.filter(code=OLD_PERMISSION_CODE).first()
    if not menu or not old_permission:
        return

    MenuPermission.objects.filter(
        menu=menu,
        permission__code=NEW_PERMISSION_CODE,
        relation_type=RELATION_VISIBILITY,
    ).update(isactive=False)

    MenuPermission.objects.update_or_create(
        menu=menu,
        permission=old_permission,
        relation_type=RELATION_VISIBILITY,
        defaults={"isactive": True},
    )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0212_repair_sales_workflow_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
