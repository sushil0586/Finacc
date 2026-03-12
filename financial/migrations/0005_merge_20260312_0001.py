from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
        ("financial", "0004_remove_legacy_static_models"),
    ]

    operations = []
