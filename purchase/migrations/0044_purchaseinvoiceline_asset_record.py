from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0005_assetbulkjob_committed_fields"),
        ("purchase", "0043_purchaseinvoiceline_purchase_behavior_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceline",
            name="asset_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="source_purchase_lines",
                to="assets.fixedasset",
            ),
        ),
    ]
