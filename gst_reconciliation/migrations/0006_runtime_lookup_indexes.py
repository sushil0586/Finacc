from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gst_reconciliation", "0005_perf_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="gstreconciliationrun",
            index=models.Index(
                fields=["entity", "reconciliation_type", "return_period", "status", "created_at"],
                name="ix_gst_run_ent_type_st_ct",
            ),
        ),
        migrations.AddIndex(
            model_name="gstreconciliationitem",
            index=models.Index(
                fields=["run", "resolution_status", "updated_at"],
                name="ix_gst_item_run_res_upd",
            ),
        ),
        migrations.AddIndex(
            model_name="gstreconciliationitem",
            index=models.Index(
                fields=["run", "match_status", "updated_at"],
                name="ix_gst_item_run_stat_upd",
            ),
        ),
        migrations.AddIndex(
            model_name="gstimportedreturn",
            index=models.Index(
                fields=["entity", "return_type", "return_period", "status", "created_at"],
                name="ix_gst_imp_ent_type_st_ct",
            ),
        ),
        migrations.AddIndex(
            model_name="gstimportedreturnrow",
            index=models.Index(
                fields=["imported_return", "counterparty_gstin_normalized", "row_no"],
                name="ix_gst_imp_row_gstin_row",
            ),
        ),
    ]
