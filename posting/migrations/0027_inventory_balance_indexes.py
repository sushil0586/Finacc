from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0026_posting_report_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="inventorymove",
            index=models.Index(
                fields=["entity", "location", "product", "batch_number"],
                name="ix_im_ent_loc_batch",
            ),
        ),
    ]
