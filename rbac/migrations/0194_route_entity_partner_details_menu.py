from django.db import migrations


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.filter(code="admin.entity_partner_details").update(
        route_path="/entity-partner-details",
        route_name="entity-partner-details",
    )


def backwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.filter(code="admin.entity_partner_details").update(
        route_path="/businesssettings",
        route_name="businesssettings",
    )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0193_resync_capital_distribution_superadmin_permissions")]

    operations = [migrations.RunPython(forwards, backwards)]
