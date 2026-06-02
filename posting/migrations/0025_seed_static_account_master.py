from django.db import migrations


def seed_static_account_master(apps, schema_editor):
    from posting.services.static_accounts import StaticAccountService

    StaticAccountService.seed_static_account_master()


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0024_alter_entry_txn_type_alter_inventorymove_txn_type_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_static_account_master, migrations.RunPython.noop),
    ]
