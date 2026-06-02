from django.core.management import call_command
from django.db import migrations


def seed_withholding_catalog(apps, schema_editor):
    call_command("seed_withholding")


class Migration(migrations.Migration):

    dependencies = [
        ("withholding", "0016_entitywithholdingconfig_tds_194q_turnover_fields"),
    ]

    operations = [
        migrations.RunPython(seed_withholding_catalog, migrations.RunPython.noop),
    ]
