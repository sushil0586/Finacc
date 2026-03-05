from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("purchase", "0016_purchase_vendor_withholding_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="base_currency_code",
            field=models.CharField(default="INR", max_length=3),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="cancel_reason",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="cancelled_purchase_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="confirmed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="confirmed_purchase_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="currency_code",
            field=models.CharField(db_index=True, default="INR", max_length=3),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="exchange_rate",
            field=models.DecimalField(decimal_places=6, default=Decimal("1.000000"), max_digits=18),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="grand_total_base_currency",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="posted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="posted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="posted_purchase_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="vendorbillopenitem",
            name="gross_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="vendorbillopenitem",
            name="gst_tds_deducted",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="vendorbillopenitem",
            name="net_payable_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="vendorbillopenitem",
            name="tds_deducted",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
    ]

