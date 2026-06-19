from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory_ops", "0006_alter_inventoryopssettings_options_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="inventorytransfer",
            index=models.Index(
                fields=["entity", "entityfin", "subentity", "status", "transfer_date"],
                name="ix_inv_transfer_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="inventoryadjustment",
            index=models.Index(
                fields=["entity", "entityfin", "subentity", "status", "adjustment_date"],
                name="ix_inv_adj_scope",
            ),
        ),
    ]
