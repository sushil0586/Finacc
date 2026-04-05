from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("withholding", "0002_withholdingsection_law_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="withholdingsection",
            name="higher_rate_206ab",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Higher rate to apply when deductee is specified person under section 206AB.",
                max_digits=7,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.0000"))],
            ),
        ),
        migrations.AddField(
            model_name="partytaxprofile",
            name="is_specified_person_206ab",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="partytaxprofile",
            name="specified_person_valid_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="partytaxprofile",
            name="specified_person_valid_to",
            field=models.DateField(blank=True, null=True),
        ),
    ]

