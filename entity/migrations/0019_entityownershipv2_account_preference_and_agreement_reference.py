from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("entity", "0018_entityconstitutionv2_account_preference_and_agreement_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="entityownershipv2",
            name="effective_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entityownershipv2",
            name="effective_to",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entityownershipv2",
            name="account_preference",
            field=models.CharField(
                choices=[("capital", "Capital"), ("current", "Current"), ("auto", "Auto")],
                default="auto",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="entityownershipv2",
            name="agreement_reference",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
