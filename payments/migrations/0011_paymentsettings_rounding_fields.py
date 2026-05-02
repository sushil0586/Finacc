from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0010_remove_paymentvoucherheader_uq_payment_voucher_entity_fin_code_no_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentsettings",
            name="enable_round_off",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="paymentsettings",
            name="round_grand_total_to",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
