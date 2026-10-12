# Generated for Phase 2C final index-removal certification on 2026-10-12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("posting", "0035_remove_plain_postingbatch_voucher_number_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP INDEX IF EXISTS public.posting_journalline_voucher_no_3c71da2e;"
            ),
            reverse_sql=(
                "CREATE INDEX IF NOT EXISTS posting_journalline_voucher_no_3c71da2e "
                "ON public.posting_journalline USING btree (voucher_no);"
            ),
            state_operations=[],
        ),
    ]
