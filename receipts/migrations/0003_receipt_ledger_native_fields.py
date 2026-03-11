from django.db import migrations, models
import django.db.models.deletion


def backfill_receipt_ledgers(apps, schema_editor):
    ReceiptVoucherHeader = apps.get_model("receipts", "ReceiptVoucherHeader")
    ReceiptVoucherAdjustment = apps.get_model("receipts", "ReceiptVoucherAdjustment")

    for row in (
        ReceiptVoucherHeader.objects
        .exclude(received_in_id__isnull=True)
        .filter(received_in_ledger_id__isnull=True)
        .select_related("received_in")
    ):
        ledger_id = getattr(getattr(row, "received_in", None), "ledger_id", None)
        if ledger_id:
            row.received_in_ledger_id = ledger_id
            row.save(update_fields=["received_in_ledger"])

    for row in (
        ReceiptVoucherHeader.objects
        .exclude(received_from_id__isnull=True)
        .filter(received_from_ledger_id__isnull=True)
        .select_related("received_from")
    ):
        ledger_id = getattr(getattr(row, "received_from", None), "ledger_id", None)
        if ledger_id:
            row.received_from_ledger_id = ledger_id
            row.save(update_fields=["received_from_ledger"])

    for row in (
        ReceiptVoucherAdjustment.objects
        .exclude(ledger_account_id__isnull=True)
        .filter(ledger_id__isnull=True)
        .select_related("ledger_account")
    ):
        ledger_id = getattr(getattr(row, "ledger_account", None), "ledger_id", None)
        if ledger_id:
            row.ledger_id = ledger_id
            row.save(update_fields=["ledger"])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
        ("receipts", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="receiptvoucherheader",
            name="received_in_ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of received_in for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receipt_vouchers_received_in", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="receiptvoucherheader",
            name="received_from_ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of received_from for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receipt_vouchers_received_from", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="receiptvoucheradjustment",
            name="ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of ledger_account for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receipt_adjustments", to="financial.ledger"),
        ),
        migrations.AddIndex(
            model_name="receiptvoucherheader",
            index=models.Index(fields=["entity", "entityfinid", "received_from_ledger"], name="ix_receipt_ent_fin_cust_led"),
        ),
        migrations.RunPython(backfill_receipt_ledgers, migrations.RunPython.noop),
    ]
