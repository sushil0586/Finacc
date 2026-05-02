from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0006_remove_receiptvoucherheader_uq_receipt_voucher_entity_fin_code_no_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="receiptsettings",
            name="enable_round_off",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="receiptsettings",
            name="round_grand_total_to",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
