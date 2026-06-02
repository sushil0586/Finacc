from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gst_reconciliation", "0004_gstreconciliationitem_assigned_by_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="gstreconciliationitem",
            index=models.Index(
                fields=["run", "assigned_reviewer", "resolution_status", "updated_at"],
                name="ix_gst_item_queue",
            ),
        ),
        migrations.AddIndex(
            model_name="gstreconciliationitem",
            index=models.Index(
                fields=["run", "counterparty_gstin", "resolution_status"],
                name="ix_gst_item_run_party_res",
            ),
        ),
        migrations.AddIndex(
            model_name="gstreconciliationitem",
            index=models.Index(
                fields=["run", "match_confidence_score"],
                name="ix_gst_item_run_conf",
            ),
        ),
        migrations.AddIndex(
            model_name="gstreconciliationactionlog",
            index=models.Index(
                fields=["item", "created_at"],
                name="ix_gst_log_item_created",
            ),
        ),
    ]
