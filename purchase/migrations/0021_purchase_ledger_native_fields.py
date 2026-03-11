from django.db import migrations, models


def backfill_purchase_ledgers(apps, schema_editor):
    PurchaseInvoiceHeader = apps.get_model("purchase", "PurchaseInvoiceHeader")
    VendorBillOpenItem = apps.get_model("purchase", "VendorBillOpenItem")
    VendorSettlement = apps.get_model("purchase", "VendorSettlement")
    VendorAdvanceBalance = apps.get_model("purchase", "VendorAdvanceBalance")
    Account = apps.get_model("financial", "account")

    account_ledger_map = {
        row["id"]: row["ledger_id"]
        for row in Account.objects.filter(ledger_id__isnull=False).values("id", "ledger_id")
    }

    for model in (
        PurchaseInvoiceHeader,
        VendorBillOpenItem,
        VendorSettlement,
        VendorAdvanceBalance,
    ):
        rows = []
        for obj in model.objects.filter(vendor_id__isnull=False, vendor_ledger_id__isnull=True).only("id", "vendor_id"):
            ledger_id = account_ledger_map.get(obj.vendor_id)
            if ledger_id:
                obj.vendor_ledger_id = ledger_id
                rows.append(obj)
        if rows:
            model.objects.bulk_update(rows, ["vendor_ledger"])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("purchase", "0020_vendoradvancebalance_and_more"),
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoiceheader",
            name="vendor_ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name="purchase_documents", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="vendorbillopenitem",
            name="vendor_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=models.PROTECT, to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="vendoradvancebalance",
            name="vendor_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=models.PROTECT, to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="vendorsettlement",
            name="vendor_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=models.PROTECT, to="financial.ledger"),
        ),
        migrations.RunPython(backfill_purchase_ledgers, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="purchaseinvoiceheader",
            index=models.Index(fields=["entity", "entityfinid", "vendor_ledger"], name="ix_pur_ent_fin_vledger"),
        ),
        migrations.AddIndex(
            model_name="purchaseinvoiceheader",
            index=models.Index(fields=["entity", "entityfinid", "vendor_ledger", "due_date"], name="ix_pur_ap_vldue"),
        ),
        migrations.AddIndex(
            model_name="vendorbillopenitem",
            index=models.Index(fields=["entity", "entityfinid", "vendor_ledger", "is_open"], name="ix_pur_ap_open_vscope"),
        ),
        migrations.AddIndex(
            model_name="vendorsettlement",
            index=models.Index(fields=["entity", "entityfinid", "vendor_ledger", "status"], name="ix_pur_settle_vscope"),
        ),
        migrations.AddIndex(
            model_name="vendoradvancebalance",
            index=models.Index(fields=["entity", "entityfinid", "vendor_ledger", "is_open"], name="ix_pur_adv_vscope"),
        ),
    ]
