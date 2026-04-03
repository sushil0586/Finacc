from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0031_alter_salesinvoiceline_product_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="affects_inventory",
            field=models.BooleanField(
                default=False,
                help_text="For CN/DN: whether inventory movement should be posted.",
            ),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="note_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("qty_return", "Quantity Return"),
                    ("price_diff", "Price Difference"),
                    ("other", "Other"),
                ],
                help_text="Applicable for Credit Note / Debit Note only",
                max_length=20,
                null=True,
            ),
        ),
    ]
