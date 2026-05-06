from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("withholding", "0014_remove_tcsquarterlyreturn_notes_and_more"),
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
