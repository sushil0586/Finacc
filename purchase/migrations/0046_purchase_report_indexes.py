from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0045_purchaseinvoiceheader_is_legacy_imported_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="purchaseinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "status", "bill_date"],
                name="ix_pur_hdr_statdt",
            ),
        ),
        migrations.AddIndex(
            model_name="purchaseinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "vendor", "status", "bill_date"],
                name="ix_pur_vend_statdt",
            ),
        ),
        migrations.AddIndex(
            model_name="purchaseinvoiceheader",
            index=models.Index(
                fields=["entity", "vendor", "supplier_invoice_date", "supplier_invoice_number"],
                name="ix_pur_vendor_supinv",
            ),
        ),
        migrations.AddIndex(
            model_name="vendorbillopenitem",
            index=models.Index(
                fields=["entity", "entityfinid", "vendor", "is_open", "due_date"],
                name="ix_pur_ap_open_vdue",
            ),
        ),
        migrations.AddIndex(
            model_name="vendorbillopenitem",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_open", "due_date"],
                name="ix_pur_ap_open_sdue",
            ),
        ),
        migrations.AddIndex(
            model_name="vendorsettlement",
            index=models.Index(
                fields=["entity", "entityfinid", "vendor", "status", "settlement_date"],
                name="ix_pur_settle_vstatdt",
            ),
        ),
        migrations.AddIndex(
            model_name="vendoradvancebalance",
            index=models.Index(
                fields=["entity", "entityfinid", "vendor", "is_open", "credit_date"],
                name="ix_pur_adv_vopendt",
            ),
        ),
        migrations.AddIndex(
            model_name="vendorsettlementline",
            index=models.Index(
                fields=["open_item", "settlement"],
                name="ix_pur_settleline_oi_set",
            ),
        ),
    ]
