from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0049_purchaseattachment_ix_purchase_attach_hdr_dt"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceline",
            name="cess_specific_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="purchaseinvoiceline",
            name="cess_type",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("ad_valorem", "Ad valorem"),
                    ("specific", "Specific"),
                    ("composite", "Composite"),
                ],
                default="none",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="purchaseinvoiceline",
            constraint=models.CheckConstraint(
                check=models.Q(("cess_specific_amount__gte", 0)),
                name="ck_pur_cess_specific_nonneg",
            ),
        ),
    ]
