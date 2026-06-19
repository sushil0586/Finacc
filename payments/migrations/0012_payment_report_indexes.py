from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0011_paymentsettings_rounding_fields"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="paymentvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "voucher_date"],
                name="ix_pay_entfin_sub_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "status", "voucher_date"],
                name="ix_pay_sub_stat_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentvoucherheader",
            index=models.Index(
                fields=["entity", "entityfinid", "paid_to", "status", "voucher_date"],
                name="ix_pay_vend_stat_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentvoucherallocation",
            index=models.Index(
                fields=["open_item", "payment_voucher"],
                name="ix_pay_alloc_oi_pv",
            ),
        ),
    ]
