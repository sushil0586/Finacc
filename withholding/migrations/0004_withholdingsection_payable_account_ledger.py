from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0014_financialsettings_reporting_policy"),
        ("withholding", "0003_withholding_206ab_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="withholdingsection",
            name="payable_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional section-specific payable account used at posting time.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="withholding_sections_as_payable_account",
                to="financial.account",
            ),
        ),
        migrations.AddField(
            model_name="withholdingsection",
            name="payable_ledger",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional section-specific payable ledger used at posting time.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="withholding_sections_as_payable_ledger",
                to="financial.ledger",
            ),
        ),
    ]
