from django.core.management import call_command
from django.db import migrations


def seed_entity_master_catalogs(apps, schema_editor):
    call_command("seed_entity_master_data")


class Migration(migrations.Migration):

    dependencies = [
        ("entity", "0031_rename_ent_notif_evt_entity_evt_idx_entity_noti_entity__bd0b29_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_entity_master_catalogs, migrations.RunPython.noop),
    ]
