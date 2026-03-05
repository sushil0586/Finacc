from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_alter_paymentsettings_policy_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="base_currency_code",
            field=models.CharField(default="INR", max_length=3),
        ),
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="currency_code",
            field=models.CharField(db_index=True, default="INR", max_length=3),
        ),
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="exchange_rate",
            field=models.DecimalField(decimal_places=6, default=Decimal("1.000000"), max_digits=18),
        ),
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="settlement_effective_amount_base_currency",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
    ]

