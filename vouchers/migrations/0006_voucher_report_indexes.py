from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vouchers", "0005_remove_voucherheader_uq_voucher_entity_fin_code_no_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="voucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "voucher_date"],
                name="ix_vch_entfin_sub_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="voucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "status", "voucher_date"],
                name="ix_vch_sub_stat_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="voucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "voucher_type", "voucher_date"],
                name="ix_vch_sub_type_dt",
            ),
        ),
    ]
