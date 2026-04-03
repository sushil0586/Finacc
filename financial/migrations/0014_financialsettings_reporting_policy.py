from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0013_model_integrity_fixes"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialsettings",
            name="reporting_policy",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Entity-level reporting policy overrides (SaaS configurable).",
            ),
        ),
    ]
