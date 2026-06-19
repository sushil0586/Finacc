from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0047_purchase_statutory_runtime_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="gstr2bimportbatch",
            index=models.Index(
                fields=["entity", "entityfinid", "subentity", "period", "id"],
                name="ix_gstr2b_batch_scope_id",
            ),
        ),
        migrations.AddIndex(
            model_name="gstr2bimportrow",
            index=models.Index(
                fields=["batch", "match_status", "id"],
                name="ix_gstr2b_row_batch_stat",
            ),
        ),
        migrations.AddIndex(
            model_name="gstr2bimportrow",
            index=models.Index(
                fields=["batch", "supplier_gstin", "supplier_invoice_number"],
                name="ix_gstr2b_row_batch_match",
            ),
        ),
    ]
