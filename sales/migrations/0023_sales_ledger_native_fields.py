from django.db import migrations, models
import django.db.models.deletion


def backfill_customer_ledgers(apps, schema_editor):
    SalesInvoiceHeader = apps.get_model("sales", "SalesInvoiceHeader")
    CustomerBillOpenItem = apps.get_model("sales", "CustomerBillOpenItem")
    CustomerSettlement = apps.get_model("sales", "CustomerSettlement")
    CustomerAdvanceBalance = apps.get_model("sales", "CustomerAdvanceBalance")

    for model in (
        SalesInvoiceHeader,
        CustomerBillOpenItem,
        CustomerSettlement,
        CustomerAdvanceBalance,
    ):
        for row in model.objects.exclude(customer_id__isnull=True).filter(customer_ledger_id__isnull=True).select_related("customer"):
            ledger_id = getattr(getattr(row, "customer", None), "ledger_id", None)
            if ledger_id:
                row.customer_ledger_id = ledger_id
                row.save(update_fields=["customer_ledger"])


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
        ("sales", "0022_customeradvancebalance_customerbillopenitem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customeradvancebalance",
            name="customer_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="customerbillopenitem",
            name="customer_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="customersettlement",
            name="customer_ledger",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="salesinvoiceheader",
            name="customer_ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales_invoices_by_ledger", to="financial.ledger"),
        ),
        migrations.AddIndex(
            model_name="customeradvancebalance",
            index=models.Index(fields=["entity", "entityfinid", "customer_ledger", "is_open"], name="ix_sales_ar_adv_led_scope"),
        ),
        migrations.AddIndex(
            model_name="customerbillopenitem",
            index=models.Index(fields=["entity", "entityfinid", "customer_ledger", "is_open"], name="ix_sales_ar_open_led_scope"),
        ),
        migrations.AddIndex(
            model_name="customersettlement",
            index=models.Index(fields=["entity", "entityfinid", "customer_ledger", "status"], name="ix_sales_ar_settle_led_scope"),
        ),
        migrations.AddIndex(
            model_name="salesinvoiceheader",
            index=models.Index(fields=["entity", "entityfinid", "subentity", "customer_ledger"], name="ix_sales_hdr_cust_ledger"),
        ),
        migrations.RunPython(backfill_customer_ledgers, migrations.RunPython.noop),
    ]
