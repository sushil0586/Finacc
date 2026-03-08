from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion

ZERO2 = Decimal('0.00')


def forward_upgrade(apps, schema_editor):
    VoucherHeader = apps.get_model('vouchers', 'VoucherHeader')
    VoucherLine = apps.get_model('vouchers', 'VoucherLine')
    VoucherSettings = apps.get_model('vouchers', 'VoucherSettings')

    type_map = {
        'CASH_PAYMENT': 'CASH',
        'CASH_RECEIPT': 'CASH',
        'BANK_PAYMENT': 'BANK',
        'BANK_RECEIPT': 'BANK',
        'JOURNAL': 'JOURNAL',
    }

    role_map = {
        'CASH': 'CASH_OFFSET',
        'BANK': 'BANK_OFFSET',
    }

    for header in VoucherHeader.objects.all().iterator():
        old_type = header.voucher_type
        new_type = type_map.get(old_type, old_type)
        if header.voucher_type != new_type:
            header.voucher_type = new_type
            header.save(update_fields=['voucher_type'])

        lines = list(VoucherLine.objects.filter(header_id=header.id).order_by('line_no', 'id'))
        if new_type == 'JOURNAL':
            for idx, line in enumerate(lines, start=1):
                amt = getattr(line, 'amount', ZERO2) or ZERO2
                line.dr_amount = amt if bool(getattr(line, 'drcr', True)) else ZERO2
                line.cr_amount = ZERO2 if bool(getattr(line, 'drcr', True)) else amt
                line.is_system_generated = False
                line.system_line_role = 'BUSINESS'
                line.pair_no = idx
                line.save(update_fields=['dr_amount', 'cr_amount', 'is_system_generated', 'system_line_role', 'pair_no'])
            continue

        max_line_no = max([int(x.line_no or 0) for x in lines], default=0)
        next_line_no = max_line_no + 1
        generated_rows = []
        for idx, line in enumerate(lines, start=1):
            amt = getattr(line, 'amount', ZERO2) or ZERO2
            is_debit = bool(getattr(line, 'drcr', True))
            line.dr_amount = amt if is_debit else ZERO2
            line.cr_amount = ZERO2 if is_debit else amt
            line.is_system_generated = False
            line.system_line_role = 'BUSINESS'
            line.pair_no = idx
            line.save(update_fields=['dr_amount', 'cr_amount', 'is_system_generated', 'system_line_role', 'pair_no'])

            line_narration = getattr(line, 'narration', None)
            header_narration = getattr(header, 'narration', None)
            if line_narration:
                offset_narration = f'Against {line_narration}'
            elif header_narration:
                offset_narration = f'Against {header_narration}'
            else:
                offset_narration = 'Auto cash offset' if new_type == 'CASH' else 'Auto bank offset'

            generated_rows.append(VoucherLine(
                header_id=header.id,
                line_no=next_line_no,
                account_id=header.cash_bank_account_id,
                narration=offset_narration,
                dr_amount=ZERO2 if is_debit else amt,
                cr_amount=amt if is_debit else ZERO2,
                is_system_generated=True,
                system_line_role=role_map[new_type],
                generated_from_line_id=line.id,
                pair_no=idx,
            ))
            next_line_no += 1

        if generated_rows:
            VoucherLine.objects.bulk_create(generated_rows)

    for setting in VoucherSettings.objects.all().iterator():
        cash_code = (getattr(setting, 'default_doc_code_cash_payment', None) or getattr(setting, 'default_doc_code_cash_receipt', None) or 'CV')
        bank_code = (getattr(setting, 'default_doc_code_bank_payment', None) or getattr(setting, 'default_doc_code_bank_receipt', None) or 'BV')
        setting.default_doc_code_cash = cash_code
        setting.default_doc_code_bank = bank_code
        setting.save(update_fields=['default_doc_code_cash', 'default_doc_code_bank'])


def backward_upgrade(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('vouchers', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='voucherheader',
            old_name='primary_account',
            new_name='cash_bank_account',
        ),
        migrations.AlterField(
            model_name='voucherheader',
            name='cash_bank_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='voucher_cash_bank_accounts', to='financial.account'),
        ),
        migrations.RenameField(
            model_name='voucherline',
            old_name='ledger_account',
            new_name='account',
        ),
        migrations.RenameField(
            model_name='voucherline',
            old_name='remarks',
            new_name='narration',
        ),
        migrations.AddField(
            model_name='voucherline',
            name='dr_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='voucherline',
            name='cr_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14),
        ),
        migrations.AddField(
            model_name='voucherline',
            name='is_system_generated',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='voucherline',
            name='system_line_role',
            field=models.CharField(choices=[('BUSINESS', 'Business'), ('CASH_OFFSET', 'Cash Offset'), ('BANK_OFFSET', 'Bank Offset')], db_index=True, default='BUSINESS', max_length=20),
        ),
        migrations.AddField(
            model_name='voucherline',
            name='generated_from_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_lines', to='vouchers.voucherline'),
        ),
        migrations.AddField(
            model_name='voucherline',
            name='pair_no',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='vouchersettings',
            name='default_doc_code_cash',
            field=models.CharField(default='CV', max_length=10),
        ),
        migrations.AddField(
            model_name='vouchersettings',
            name='default_doc_code_bank',
            field=models.CharField(default='BV', max_length=10),
        ),
        migrations.RunPython(forward_upgrade, backward_upgrade),
        migrations.AlterField(
            model_name='voucherheader',
            name='voucher_type',
            field=models.CharField(choices=[('JOURNAL', 'Journal'), ('CASH', 'Cash'), ('BANK', 'Bank')], db_index=True, default='JOURNAL', max_length=20),
        ),
        migrations.RemoveField(
            model_name='voucherline',
            name='drcr',
        ),
        migrations.RemoveField(
            model_name='voucherline',
            name='amount',
        ),
        migrations.RemoveField(
            model_name='vouchersettings',
            name='default_doc_code_cash_payment',
        ),
        migrations.RemoveField(
            model_name='vouchersettings',
            name='default_doc_code_cash_receipt',
        ),
        migrations.RemoveField(
            model_name='vouchersettings',
            name='default_doc_code_bank_payment',
        ),
        migrations.RemoveField(
            model_name='vouchersettings',
            name='default_doc_code_bank_receipt',
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS ix_voucher_line_ledger;',
                    reverse_sql='',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE vouchers_voucherline DROP CONSTRAINT IF EXISTS ck_voucher_line_amt_nonneg;',
                    reverse_sql='',
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='voucherline',
                    name='ix_voucher_line_ledger',
                ),
                migrations.RemoveConstraint(
                    model_name='voucherline',
                    name='ck_voucher_line_amt_nonneg',
                ),
            ],
        ),
        migrations.AddIndex(
            model_name='voucherline',
            index=models.Index(fields=['account'], name='ix_voucher_line_account'),
        ),
        migrations.AddIndex(
            model_name='voucherline',
            index=models.Index(fields=['header', 'is_system_generated'], name='ix_voucher_line_hdr_sys'),
        ),
        migrations.AddConstraint(
            model_name='voucherline',
            constraint=models.CheckConstraint(check=models.Q(('dr_amount__gte', 0)), name='ck_voucher_line_dr_nonneg'),
        ),
        migrations.AddConstraint(
            model_name='voucherline',
            constraint=models.CheckConstraint(check=models.Q(('cr_amount__gte', 0)), name='ck_voucher_line_cr_nonneg'),
        ),
    ]
