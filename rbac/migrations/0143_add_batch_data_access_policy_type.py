from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0142_repair_sales_unpost_admin_permissions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dataaccesspolicy",
            name="policy_type",
            field=models.CharField(
                choices=[
                    ("branch", "Branch"),
                    ("department", "Department"),
                    ("warehouse", "Warehouse"),
                    ("batch", "Batch"),
                    ("financial_year", "Financial Year"),
                    ("custom", "Custom"),
                ],
                max_length=30,
            ),
        ),
    ]
