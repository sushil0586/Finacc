from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0046_purchase_report_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="purchasestatutorychallan",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "tax_type", "status", "challan_date"],
                name="ix_pur_stat_ch_scope_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasestatutorychallanline",
            index=models.Index(
                fields=["header", "challan"],
                name="ix_pur_stcl_hdr_ch",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasestatutoryreturn",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "tax_type", "status", "period_to"],
                name="ix_pur_stat_ret_scope_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasestatutoryreturn",
            index=models.Index(
                fields=["original_return", "revision_no"],
                name="ix_pur_stat_ret_orig_rev",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasestatutoryreturn",
            index=models.Index(
                fields=["original_return", "status"],
                name="ix_pur_stat_ret_orig_stat",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasestatutoryreturnline",
            index=models.Index(
                fields=["challan", "header"],
                name="ix_pur_stat_rl_ch_hdr",
            ),
        ),
    ]
