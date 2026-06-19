from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0007_receiptsettings_rounding_fields"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="receiptvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "voucher_date"],
                name="ix_rec_entfin_sub_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "status", "voucher_date"],
                name="ix_rec_sub_stat_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "received_from", "status", "voucher_date"],
                name="ix_rec_cust_stat_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptvoucherallocation",
            index=models.Index(
                fields=["open_item", "receipt_voucher"],
                name="ix_rec_alloc_oi_rv",
            ),
        ),
    ]
