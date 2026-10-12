# Generated for Phase 2C index-removal certification on 2026-10-12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0034_remove_plain_voucher_number_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP INDEX IF EXISTS public.posting_postingbatch_voucher_no_301c24a6;"
            ),
            reverse_sql=(
                "CREATE INDEX IF NOT EXISTS posting_postingbatch_voucher_no_301c24a6 "
                "ON public.posting_postingbatch USING btree (voucher_no);"
            ),
            state_operations=[],
        ),
    ]
