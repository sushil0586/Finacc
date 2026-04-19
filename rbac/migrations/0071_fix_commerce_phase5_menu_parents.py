from django.db import migrations


CATALOG_VERSION = "commerce_phase5_menu_fix_2026_04_18"
SEED_TAG = "commerce_phase5_menu_fix_seed"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    admin_parent = Menu.objects.filter(code="admin", isactive=True).first()
    if admin_parent is None:
        return

    permission = Permission.objects.filter(code="commerce.promotion.view", isactive=True).first()

    menu, _ = Menu.objects.update_or_create(
        code="admin.commerce_promotions",
        defaults={
            "parent_id": admin_parent.id,
            "name": "Commerce Promotions",
            "menu_type": "screen",
            "route_path": "/commerce-promotions",
            "route_name": "commerce-promotions",
            "icon": "badge-percent",
            "sort_order": 13,
            "is_system_menu": True,
            "metadata": {
                "seed": SEED_TAG,
                "catalog_version": CATALOG_VERSION,
                "menu_code": "admin.commerce_promotions",
                "permission_code": "commerce.promotion.view",
            },
            "isactive": True,
        },
    )

    if permission is not None:
        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type="visibility",
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0070_add_commerce_phase5_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
