from django.db import migrations, models
import payments.models.payment_config


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentsettings",
            name="policy_controls",
            field=models.JSONField(blank=True, default=payments.models.payment_config.default_payment_policy_controls),
        ),
    ]
