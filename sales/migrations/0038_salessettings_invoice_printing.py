from django.db import migrations, models

import sales.models.sales_settings


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0037_salesinvoiceline_ix_sales_line_hdr_srv"),
    ]

    operations = [
        migrations.AddField(
            model_name="salessettings",
            name="invoice_printing",
            field=models.JSONField(blank=True, default=sales.models.sales_settings.default_invoice_printing),
        ),
    ]

