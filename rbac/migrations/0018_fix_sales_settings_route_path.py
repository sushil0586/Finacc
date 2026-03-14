from django.db import migrations


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.filter(code="sales.configuration.settings").update(
        route_path="/sales-settings",
        route_name="sales-settings",
        isactive=True,
    )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.filter(code="sales.configuration.settings").update(
        route_path="sales-settings",
        route_name="sales-settings",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0017_seed_frontend_permission_catalog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
