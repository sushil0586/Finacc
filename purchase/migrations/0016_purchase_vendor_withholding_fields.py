from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0015_statutory_reporting_enhancements"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_base_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_cgst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_declared",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_igst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_notes",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_rate",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=7),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_gst_tds_sgst_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_tds_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_tds_base_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_tds_declared",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_tds_notes",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_tds_rate",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=7),
        ),
    ]
