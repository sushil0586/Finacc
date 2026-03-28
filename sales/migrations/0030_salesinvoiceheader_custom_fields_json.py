# Generated manually for invoice custom fields phase-1

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0029_salesinvoiceheader_ecm_gstin"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="custom_fields_json",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
