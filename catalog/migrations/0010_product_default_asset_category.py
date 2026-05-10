from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0005_assetbulkjob_committed_fields"),
        ("catalog", "0009_product_purchase_behavior"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="default_asset_category",
            field=models.ForeignKey(
                blank=True,
                help_text="Required when purchase behavior is Asset. Used to create asset intake/CWIP records from purchase posting.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="default_products",
                to="assets.assetcategory",
            ),
        ),
    ]
