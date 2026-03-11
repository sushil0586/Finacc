from django.db import migrations, models
import django.db.models.deletion


def backfill_payment_ledgers(apps, schema_editor):
    PaymentVoucherHeader = apps.get_model("payments", "PaymentVoucherHeader")
    PaymentVoucherAdjustment = apps.get_model("payments", "PaymentVoucherAdjustment")

    for row in (
        PaymentVoucherHeader.objects
        .exclude(paid_from_id__isnull=True)
        .filter(paid_from_ledger_id__isnull=True)
        .select_related("paid_from")
    ):
        ledger_id = getattr(getattr(row, "paid_from", None), "ledger_id", None)
        if ledger_id:
            row.paid_from_ledger_id = ledger_id
            row.save(update_fields=["paid_from_ledger"])

    for row in (
        PaymentVoucherHeader.objects
        .exclude(paid_to_id__isnull=True)
        .filter(paid_to_ledger_id__isnull=True)
        .select_related("paid_to")
    ):
        ledger_id = getattr(getattr(row, "paid_to", None), "ledger_id", None)
        if ledger_id:
            row.paid_to_ledger_id = ledger_id
            row.save(update_fields=["paid_to_ledger"])

    for row in (
        PaymentVoucherAdjustment.objects
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
        ("payments", "0007_paymentvoucheradvanceadjustment"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="paid_from_ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of paid_from for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_vouchers_paid_from", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="paymentvoucherheader",
            name="paid_to_ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of paid_to for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_vouchers_paid_to", to="financial.ledger"),
        ),
        migrations.AddField(
            model_name="paymentvoucheradjustment",
            name="ledger",
            field=models.ForeignKey(blank=True, help_text="Additive ledger-native mirror of ledger_account for the staged accounting cutover.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_adjustments", to="financial.ledger"),
        ),
        migrations.AddIndex(
            model_name="paymentvoucherheader",
            index=models.Index(fields=["entity", "entityfinid", "paid_to_ledger"], name="ix_pay_ent_fin_vendor_led"),
        ),
        migrations.RunPython(backfill_payment_ledgers, migrations.RunPython.noop),
    ]
