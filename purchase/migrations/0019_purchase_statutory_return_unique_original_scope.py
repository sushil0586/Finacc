from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("purchase", "0018_purchasestatutoryreturnline_deductee_country_code_snapshot_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="purchasestatutoryreturn",
            constraint=models.UniqueConstraint(
                fields=(
                    "entity",
                    "entityfinid",
                    "subentity",
                    "tax_type",
                    "return_code",
                    "period_from",
                    "period_to",
                ),
                condition=Q(original_return__isnull=True, subentity__isnull=False) & ~Q(status=9),
                name="uq_pur_stret_orig_sub_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasestatutoryreturn",
            constraint=models.UniqueConstraint(
                fields=(
                    "entity",
                    "entityfinid",
                    "tax_type",
                    "return_code",
                    "period_from",
                    "period_to",
                ),
                condition=Q(original_return__isnull=True, subentity__isnull=True) & ~Q(status=9),
                name="uq_pur_stret_orig_nsub_scope",
            ),
        ),
    ]
