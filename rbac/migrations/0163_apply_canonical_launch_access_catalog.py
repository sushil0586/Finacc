from django.db import migrations


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0162_add_gst_compliance_center_menu"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

