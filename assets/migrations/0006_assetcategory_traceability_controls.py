from django.db import migrations, models

import assets.models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0005_assetbulkjob_committed_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetcategory",
            name="traceability_controls",
            field=models.JSONField(blank=True, default=assets.models.default_asset_category_traceability_controls),
        ),
    ]
