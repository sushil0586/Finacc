from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0047_sales_invoice_list_index"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE sales_invoice_line
                    ADD COLUMN IF NOT EXISTS cess_type varchar(20) DEFAULT 'none';
                    """,
                    reverse_sql="""
                    ALTER TABLE sales_invoice_line
                    DROP COLUMN IF EXISTS cess_type;
                    """,
                ),
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE sales_invoice_line
                    ADD COLUMN IF NOT EXISTS cess_specific_amount numeric(18,2) DEFAULT 0.00;
                    """,
                    reverse_sql="""
                    ALTER TABLE sales_invoice_line
                    DROP COLUMN IF EXISTS cess_specific_amount;
                    """,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="salesinvoiceline",
                    name="cess_specific_amount",
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
                ),
                migrations.AddField(
                    model_name="salesinvoiceline",
                    name="cess_type",
                    field=models.CharField(
                        choices=[
                            ("none", "None"),
                            ("ad_valorem", "Ad Valorem"),
                            ("specific", "Specific"),
                            ("composite", "Composite"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                migrations.RemoveConstraint(
                    model_name="salesinvoiceline",
                    name="ck_sales_line_nonneg_and_rate",
                ),
                migrations.AddConstraint(
                    model_name="salesinvoiceline",
                    constraint=models.CheckConstraint(
                        check=(
                            models.Q(("qty__gte", 0))
                            & models.Q(("free_qty__gte", 0))
                            & models.Q(("rate__gte", 0))
                            & models.Q(("discount_percent__gte", 0))
                            & models.Q(("discount_percent__lte", 100))
                            & models.Q(("discount_amount__gte", 0))
                            & models.Q(("gst_rate__gte", 0))
                            & models.Q(("gst_rate__lte", 100))
                            & models.Q(("cess_percent__gte", 0))
                            & models.Q(("cess_percent__lte", 100))
                            & models.Q(("cess_specific_amount__gte", 0))
                            & models.Q(("taxable_value__gte", 0))
                            & models.Q(("cgst_amount__gte", 0))
                            & models.Q(("sgst_amount__gte", 0))
                            & models.Q(("igst_amount__gte", 0))
                            & models.Q(("cess_amount__gte", 0))
                            & models.Q(("line_total__gte", 0))
                        ),
                        name="ck_sales_line_nonneg_and_rate",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE sales_invoice_line
            DROP CONSTRAINT IF EXISTS ck_sales_line_nonneg_and_rate;
            ALTER TABLE sales_invoice_line
            ADD CONSTRAINT ck_sales_line_nonneg_and_rate CHECK (
                qty >= 0
                AND free_qty >= 0
                AND rate >= 0
                AND discount_percent >= 0
                AND discount_percent <= 100
                AND discount_amount >= 0
                AND gst_rate >= 0
                AND gst_rate <= 100
                AND cess_percent >= 0
                AND cess_percent <= 100
                AND cess_specific_amount >= 0
                AND taxable_value >= 0
                AND cgst_amount >= 0
                AND sgst_amount >= 0
                AND igst_amount >= 0
                AND cess_amount >= 0
                AND line_total >= 0
            );
            """,
            reverse_sql="""
            ALTER TABLE sales_invoice_line
            DROP CONSTRAINT IF EXISTS ck_sales_line_nonneg_and_rate;
            ALTER TABLE sales_invoice_line
            ADD CONSTRAINT ck_sales_line_nonneg_and_rate CHECK (
                qty >= 0
                AND free_qty >= 0
                AND rate >= 0
                AND discount_percent >= 0
                AND discount_percent <= 100
                AND discount_amount >= 0
                AND gst_rate >= 0
                AND gst_rate <= 100
                AND cess_percent >= 0
                AND cess_percent <= 100
                AND taxable_value >= 0
                AND cgst_amount >= 0
                AND sgst_amount >= 0
                AND igst_amount >= 0
                AND cess_amount >= 0
                AND line_total >= 0
            );
            """,
        ),
    ]
