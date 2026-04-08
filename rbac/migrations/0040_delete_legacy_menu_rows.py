from django.db import migrations


CURRENT_CATALOG_VERSION = "route_catalog_2026_04"


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    Menu.objects.exclude(metadata__catalog_version=CURRENT_CATALOG_VERSION).delete()


def backwards(apps, schema_editor):
    # Destructive cleanup; no reverse reconstruction.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0039_cleanup_excluded_route_catalog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
