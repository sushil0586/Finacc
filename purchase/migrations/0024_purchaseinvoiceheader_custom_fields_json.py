# Generated manually for invoice custom fields phase-1

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0023_purchaseinvoiceheader_uq_purchase_doc_root_type_code_no"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="custom_fields_json",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
