from django.core.management import call_command
from django.db import migrations


def seed_global_payroll_catalog(apps, schema_editor):
    call_command("seed_global_payroll_catalog")


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0018_contracttaxdeclaration_approval_status_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_global_payroll_catalog, migrations.RunPython.noop),
    ]
