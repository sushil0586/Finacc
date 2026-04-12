from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0009_alter_entitystaticaccountmap_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventorymove",
            name="source_location",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.godown"),
        ),
        migrations.AddField(
            model_name="inventorymove",
            name="destination_location",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="entity.godown"),
        ),
        migrations.AddField(
            model_name="inventorymove",
            name="movement_nature",
            field=models.CharField(
                choices=[
                    ("PURCHASE", "Purchase"),
                    ("SALE", "Sale"),
                    ("TRANSFER", "Transfer"),
                    ("ADJUSTMENT", "Adjustment"),
                    ("OPENING", "Opening Stock"),
                    ("RETURN", "Return"),
                    ("REVERSAL", "Reversal"),
                    ("OTHER", "Other"),
                ],
                db_index=True,
                default="OTHER",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="inventorymove",
            name="movement_group",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="inventorymove",
            name="movement_reason",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
        ),
    ]
