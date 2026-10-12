# Generated for Phase 2C index-removal certification on 2026-10-12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0051_remove_salestaxsummary_ix_sales_taxsum_hdr"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP INDEX IF EXISTS public.sales_invoice_header_invoice_number_239769e2;"
            ),
            reverse_sql=(
                "CREATE INDEX IF NOT EXISTS sales_invoice_header_invoice_number_239769e2 "
                "ON public.sales_invoice_header USING btree (invoice_number);"
            ),
            state_operations=[],
        ),
    ]
