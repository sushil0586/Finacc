from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0015_remove_account_ck_account_openingbcr_nonneg_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountcomplianceprofile",
            name="has_written_payment_terms",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="accountcomplianceprofile",
            name="msme_credit_days",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(45)],
            ),
        ),
        migrations.AddField(
            model_name="accountcomplianceprofile",
            name="msme_status",
            field=models.CharField(
                blank=True,
                choices=[("non_msme", "Non-MSME"), ("micro", "Micro"), ("small", "Small")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="accountcomplianceprofile",
            name="udyam_no",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
    ]
