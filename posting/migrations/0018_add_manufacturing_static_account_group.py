from django.db import migrations


def move_manufacturing_codes_to_group(apps, schema_editor):
    StaticAccount = apps.get_model("posting", "StaticAccount")
    StaticAccount.objects.filter(
        code__in=[
            "MANUFACTURING_WIP",
            "MANUFACTURING_CONSUMPTION",
            "MANUFACTURING_OVERHEAD_ABSORPTION",
            "MANUFACTURING_FINISHED_GOODS",
        ]
    ).update(group="MANUFACTURING")


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0017_seed_manufacturing_static_accounts"),
    ]

    operations = [
        migrations.RunPython(move_manufacturing_codes_to_group, migrations.RunPython.noop),
    ]
