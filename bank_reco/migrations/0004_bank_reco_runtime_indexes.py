from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bank_reco", "0003_bankstatementline_created_voucher_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="bankstatementline",
            index=models.Index(
                fields=["statement_import", "validation_status", "txn_date"],
                name="ix_bsl_stmt_val_txn",
            ),
        ),
        migrations.AddIndex(
            model_name="bankreconciliationrun",
            index=models.Index(
                fields=["statement_import", "created_at", "id"],
                name="ix_brr_stmt_latest",
            ),
        ),
    ]
