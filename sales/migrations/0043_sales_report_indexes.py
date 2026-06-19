from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0042_delete_legacy_sales_compliance_models"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "status", "bill_date"],
                name="ix_sales_hdr_stdt",
            ),
        ),
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "customer", "status", "bill_date"],
                name="ix_sales_cst_stdt",
            ),
        ),
        migrations.AddIndex(
            model_name="customerbillopenitem",
            index=models.Index(
                fields=["entity", "entityfinid", "customer", "is_open", "due_date"],
                name="ix_sales_ar_cst_due",
            ),
        ),
        migrations.AddIndex(
            model_name="customerbillopenitem",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "is_open", "due_date"],
                name="ix_sales_ar_sub_due",
            ),
        ),
        migrations.AddIndex(
            model_name="customersettlement",
            index=models.Index(
                fields=["entity", "entityfinid", "customer", "status", "settlement_date"],
                name="ix_sales_ar_stldt",
            ),
        ),
        migrations.AddIndex(
            model_name="customeradvancebalance",
            index=models.Index(
                fields=["entity", "entityfinid", "customer", "is_open", "credit_date"],
                name="ix_sales_ar_advdt",
            ),
        ),
        migrations.AddIndex(
            model_name="customersettlementline",
            index=models.Index(
                fields=["open_item", "settlement"],
                name="ix_sales_stl_oi_set",
            ),
        ),
    ]
