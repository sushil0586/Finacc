from django.core.management import call_command
from django.db import migrations


def seed_global_hrms_catalog(apps, schema_editor):
    call_command("seed_global_hrms_catalog")


class Migration(migrations.Migration):

    dependencies = [
        ("hrms", "0007_holiday_calendar_period_range"),
    ]

    operations = [
        migrations.RunPython(seed_global_hrms_catalog, migrations.RunPython.noop),
    ]
