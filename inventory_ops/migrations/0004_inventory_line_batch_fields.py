from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory_ops", "0003_alter_inventoryadjustment_location_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventoryadjustmentline",
            name="batch_number",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="inventoryadjustmentline",
            name="expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventoryadjustmentline",
            name="manufacture_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventorytransferline",
            name="batch_number",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="inventorytransferline",
            name="expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventorytransferline",
            name="manufacture_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
