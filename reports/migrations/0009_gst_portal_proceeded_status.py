from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0008_gst_portal_profile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gstportalfilingrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("prepared", "Prepared"),
                    ("saved", "Saved"),
                    ("proceeded", "Proceeded"),
                    ("summary_fetched", "Summary Fetched"),
                    ("offset", "Offset"),
                    ("evc_requested", "EVC Requested"),
                    ("filed", "Filed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="prepared",
                max_length=24,
            ),
        ),
    ]
