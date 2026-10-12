# Generated for Phase 2C index-removal certification on 2026-10-12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0033_remove_journalline_ix_jl_posting_ledger"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP INDEX IF EXISTS public.posting_entry_voucher_no_6a95f765;"
            ),
            reverse_sql=(
                "CREATE INDEX IF NOT EXISTS posting_entry_voucher_no_6a95f765 "
                "ON public.posting_entry USING btree (voucher_no);"
            ),
            state_operations=[],
        ),
    ]
