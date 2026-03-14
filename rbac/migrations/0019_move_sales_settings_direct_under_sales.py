from django.db import migrations


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    sales_menu = Menu.objects.filter(code="sales", isactive=True).first()
    settings_menu = Menu.objects.filter(code="sales.configuration.settings").first()
    config_menu = Menu.objects.filter(code="sales.configuration").first()

    if sales_menu and settings_menu:
        settings_menu.parent_id = sales_menu.id
        settings_menu.sort_order = 2
        settings_menu.route_path = "/sales-settings"
        settings_menu.route_name = "sales-settings"
        settings_menu.isactive = True
        settings_menu.save(update_fields=["parent", "sort_order", "route_path", "route_name", "isactive", "updated_at"])

    if config_menu:
        config_menu.isactive = False
        config_menu.save(update_fields=["isactive", "updated_at"])


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    sales_menu = Menu.objects.filter(code="sales", isactive=True).first()
    config_menu = Menu.objects.filter(code="sales.configuration").first()
    settings_menu = Menu.objects.filter(code="sales.configuration.settings").first()

    if config_menu:
        config_menu.isactive = True
        config_menu.parent_id = sales_menu.id if sales_menu else config_menu.parent_id
        config_menu.sort_order = 2
        config_menu.route_path = ""
        config_menu.route_name = "sales-configuration"
        config_menu.save(update_fields=["isactive", "parent", "sort_order", "route_path", "route_name", "updated_at"])

    if config_menu and settings_menu:
        settings_menu.parent_id = config_menu.id
        settings_menu.sort_order = 1
        settings_menu.route_path = "/sales-settings"
        settings_menu.route_name = "sales-settings"
        settings_menu.isactive = True
        settings_menu.save(update_fields=["parent", "sort_order", "route_path", "route_name", "isactive", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0018_fix_sales_settings_route_path"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
