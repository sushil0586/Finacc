from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0023_sales_ledger_native_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="salessettings",
            name="policy_controls",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
