from django.db import migrations


MENU_RELATION_VISIBILITY = "visibility"
CATALOG_VERSION = "manufacturing_route_menu_2026_04_18"
SEED_TAG = "manufacturing_route_menu_seed"


MENU_SPECS = [
    {
        "code": "inventory.manufacturing_routes",
        "name": "Manufacturing Routes",
        "parent_code": "inventory.operations",
        "route_path": "/manufacturing-routes",
        "route_name": "manufacturing-routes",
        "icon": "route",
        "sort_order": 6,
        "permission_code": "manufacturing.bom.view",
    },
    {
        "code": "reports.inventory.manufacturing_routes",
        "name": "Manufacturing Routes",
        "parent_code": "reports.inventory",
        "route_path": "/manufacturing-routes",
        "route_name": "manufacturing-routes",
        "icon": "route",
        "sort_order": 10,
        "permission_code": "manufacturing.bom.view",
    },
]


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")
    Permission = apps.get_model("rbac", "Permission")

    permission = Permission.objects.filter(code="manufacturing.bom.view", isactive=True).first()
    if permission is None:
        return

    for spec in MENU_SPECS:
        parent_menu = Menu.objects.filter(code=spec["parent_code"], isactive=True).first()
        if parent_menu is None:
            continue

        menu, _ = Menu.objects.update_or_create(
            code=spec["code"],
            defaults={
                "parent_id": parent_menu.id,
                "name": spec["name"],
                "menu_type": "screen",
                "route_path": spec["route_path"],
                "route_name": spec["route_name"],
                "icon": spec["icon"],
                "sort_order": spec["sort_order"],
                "is_system_menu": True,
                "metadata": {
                    "seed": SEED_TAG,
                    "catalog_version": CATALOG_VERSION,
                    "menu_code": spec["code"],
                    "permission_code": spec["permission_code"],
                },
                "isactive": True,
            },
        )

        MenuPermission.objects.update_or_create(
            menu_id=menu.id,
            permission_id=permission.id,
            relation_type=MENU_RELATION_VISIBILITY,
            defaults={"isactive": True},
        )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    menu_ids = list(Menu.objects.filter(code__in=[spec["code"] for spec in MENU_SPECS]).values_list("id", flat=True))
    if menu_ids:
        MenuPermission.objects.filter(menu_id__in=menu_ids).delete()
    Menu.objects.filter(code__in=[spec["code"] for spec in MENU_SPECS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0068_seed_live_manufacturing_menus"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
