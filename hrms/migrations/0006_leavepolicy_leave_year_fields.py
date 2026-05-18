from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("hrms", "0005_leaveapplication_approval_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="leavepolicy",
            name="leave_year_type",
            field=models.CharField(
                choices=[
                    ("calendar_year", "Calendar Year"),
                    ("financial_year", "Financial Year"),
                    ("custom_range", "Custom Range"),
                ],
                default="financial_year",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="leavepolicy",
            name="year_end_day",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)],
            ),
        ),
        migrations.AddField(
            model_name="leavepolicy",
            name="year_end_month",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)],
            ),
        ),
        migrations.AddField(
            model_name="leavepolicy",
            name="year_start_day",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)],
            ),
        ),
        migrations.AddField(
            model_name="leavepolicy",
            name="year_start_month",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)],
            ),
        ),
    ]
