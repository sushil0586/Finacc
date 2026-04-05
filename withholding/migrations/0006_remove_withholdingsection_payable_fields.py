from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("withholding", "0005_entitywithholdingsectionpostingmap"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="withholdingsection",
            name="payable_account",
        ),
        migrations.RemoveField(
            model_name="withholdingsection",
            name="payable_ledger",
        ),
    ]
