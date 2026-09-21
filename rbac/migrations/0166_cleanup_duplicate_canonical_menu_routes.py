from django.db import migrations


def forwards(apps, schema_editor):
    from rbac.canonical_seeding import CanonicalRBACCatalogSeedService

    CanonicalRBACCatalogSeedService.seed_global_catalog()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0165_resync_launch_role_route_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
