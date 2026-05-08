from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0008_manufacturingworkorder_lifecycle_audit_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="manufacturingworkorder",
            name="capitalized_additional_cost_snapshot",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=18),
        ),
        migrations.AddField(
            model_name="manufacturingworkorder",
            name="expensed_additional_cost_snapshot",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=18),
        ),
    ]
