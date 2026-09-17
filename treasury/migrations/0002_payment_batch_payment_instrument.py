from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0020_financial_master_runtime_indexes"),
        ("payments", "0015_paymentvoucherheader_ix_pay_ref_warn_scope"),
        ("treasury", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="treasurypaymentbatch",
            name="instrument_bank_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="treasurypaymentbatch",
            name="instrument_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="treasurypaymentbatch",
            name="instrument_no",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="treasurypaymentbatch",
            name="paid_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="treasury_payment_batches_paid_from",
                to="financial.account",
            ),
        ),
        migrations.AddField(
            model_name="treasurypaymentbatch",
            name="payment_mode",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="treasury_payment_batches",
                to="payments.paymentmode",
            ),
        ),
    ]
