from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0043_sales_report_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "bill_date", "doc_code", "doc_no"],
                name="ix_sales_hdr_bdt_nav",
            ),
        ),
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "supply_category", "bill_date"],
                name="ix_sales_hdr_sup_bdt",
            ),
        ),
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "place_of_supply_state_code", "bill_date"],
                name="ix_sales_hdr_pos_bdt",
            ),
        ),
        migrations.AddIndex(
            model_name="salesinvoiceline",
            index=models.Index(
                fields=["header", "hsn_sac_code", "is_service", "gst_rate"],
                name="ix_sales_line_hdr_hsn",
            ),
        ),
        migrations.AddIndex(
            model_name="salestaxsummary",
            index=models.Index(
                fields=["header", "gst_rate", "taxability", "hsn_sac_code"],
                name="ix_sales_taxsum_bucket",
            ),
        ),
        migrations.AddIndex(
            model_name="salesadvanceadjustment",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_amendment", "entry_type", "voucher_date"],
                name="ix_sales_adv_typ_date",
            ),
        ),
        migrations.AddIndex(
            model_name="salesadvanceadjustment",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "entry_type", "voucher_number"],
                name="ix_sales_adv_typ_vno",
            ),
        ),
        migrations.AddIndex(
            model_name="salesecommercesupply",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_amendment", "invoice_date"],
                name="ix_sales_eco_amd_date",
            ),
        ),
        migrations.AddIndex(
            model_name="salesecommercesupply",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_amendment", "supplier_eco_gstin"],
                name="ix_sales_eco_amd_sup",
            ),
        ),
        migrations.AddIndex(
            model_name="salesecommercesupply",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_amendment", "operator_gstin", "supply_split"],
                name="ix_sales_eco_amd_opsp",
            ),
        ),
    ]
