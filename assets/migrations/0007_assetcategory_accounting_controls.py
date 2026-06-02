from django.db import migrations, models

import assets.models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_assetcategory_traceability_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetcategory",
            name="accounting_controls",
            field=models.JSONField(blank=True, default=assets.models.default_asset_category_accounting_controls),
        ),
    ]
