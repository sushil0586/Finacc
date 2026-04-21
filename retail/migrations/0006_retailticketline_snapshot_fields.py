from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("retail", "0005_retailclosebatch_retailclosebatchticket_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="retailticketline",
            name="product_desc_snapshot",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="retailticketline",
            name="product_hsn_snapshot",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]
