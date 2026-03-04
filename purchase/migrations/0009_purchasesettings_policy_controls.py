from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0008_purchasesettings_post_gst_tds_on_invoice"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasesettings",
            name="policy_controls",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

