from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("withholding", "0011_entitywithholdingconfig_tcs_206c1h_force_eligible_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tcsquarterlyreturn",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tcsquarterlyreturn",
            name="original_return",
            field=models.ForeignKey(
                blank=True,
                help_text="For CORRECTION returns: reference to the original return being revised.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="corrections",
                to="withholding.tcsquarterlyreturn",
            ),
        ),
    ]
