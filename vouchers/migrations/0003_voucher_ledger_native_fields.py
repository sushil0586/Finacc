from django.db import migrations, models
import django.db.models.deletion


def backfill_voucher_ledgers(apps, schema_editor):
    VoucherHeader = apps.get_model("vouchers", "VoucherHeader")
    VoucherLine = apps.get_model("vouchers", "VoucherLine")

    for header in VoucherHeader.objects.select_related("cash_bank_account").all().iterator():
        ledger_id = getattr(header.cash_bank_account, "ledger_id", None)
        if ledger_id and header.cash_bank_ledger_id != ledger_id:
            VoucherHeader.objects.filter(pk=header.pk).update(cash_bank_ledger_id=ledger_id)

    for line in VoucherLine.objects.select_related("account").all().iterator():
        ledger_id = getattr(line.account, "ledger_id", None)
        if ledger_id and line.ledger_id != ledger_id:
            VoucherLine.objects.filter(pk=line.pk).update(ledger_id=ledger_id)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("financial", "0004_account_uq_account_entity_accountcode_present"),
        ("vouchers", "0002_final_voucher_design"),
    ]

    operations = [
        migrations.AddField(
            model_name="voucherheader",
            name="cash_bank_ledger",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="voucher_cash_bank_ledgers",
                to="financial.ledger",
            ),
        ),
        migrations.AddField(
            model_name="voucherline",
            name="ledger",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="voucher_lines_ledgers",
                to="financial.ledger",
            ),
        ),
        migrations.RunPython(backfill_voucher_ledgers, migrations.RunPython.noop),
    ]
