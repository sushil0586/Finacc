from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0040_salesinvoiceheader_is_legacy_imported_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleseinvoice",
            name="credential_gstin",
            field=models.CharField(blank=True, db_index=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name="saleseinvoice",
            name="provider_environment",
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, "Sandbox"), (2, "Production")], db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="saleseinvoice",
            name="provider_name",
            field=models.CharField(blank=True, db_index=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="salesewaybill",
            name="credential_gstin",
            field=models.CharField(blank=True, db_index=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name="salesewaybill",
            name="provider_environment",
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, "Sandbox"), (2, "Production")], db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="salesewaybill",
            name="provider_name",
            field=models.CharField(blank=True, db_index=True, max_length=40, null=True),
        ),
    ]
