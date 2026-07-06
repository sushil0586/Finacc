from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0046_salesinvoiceline_taxability"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "doc_no"],
                name="ix_sales_hdr_scope_docno",
            ),
        ),
    ]
