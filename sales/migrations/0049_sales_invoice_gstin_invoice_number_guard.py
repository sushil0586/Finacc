from django.db import migrations, models
from django.db.models import Count


def audit_duplicate_seller_gstin_invoice_numbers(apps, schema_editor):
    SalesInvoiceHeader = apps.get_model("sales", "SalesInvoiceHeader")

    duplicates = (
        SalesInvoiceHeader.objects.filter(
            is_active=True,
            seller_gstin__isnull=False,
            invoice_number__isnull=False,
        )
        .exclude(seller_gstin="")
        .exclude(invoice_number="")
        .values("entity_id", "entityfinid_id", "doc_type", "seller_gstin", "invoice_number")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("entity_id", "entityfinid_id", "doc_type", "seller_gstin", "invoice_number")[:10]
    )

    duplicate_samples = list(duplicates)
    if duplicate_samples:
        sample_text = "; ".join(
            (
                f"entity={item['entity_id']}, fy={item['entityfinid_id']}, "
                f"doc_type={item['doc_type']}, seller_gstin={item['seller_gstin']}, "
                f"invoice_number={item['invoice_number']}, rows={item['row_count']}"
            )
            for item in duplicate_samples
        )
        raise RuntimeError(
            "Cannot add sales GSTIN invoice-number uniqueness guard because duplicate "
            f"active invoice numbers already exist. Samples: {sample_text}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0048_salesinvoiceline_cess_type_and_specific_amount"),
    ]

    operations = [
        migrations.RunPython(audit_duplicate_seller_gstin_invoice_numbers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="salesinvoiceheader",
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(
                        ("invoice_number__isnull", False),
                        ("is_active", True),
                        ("seller_gstin__isnull", False),
                    )
                    & ~models.Q(("seller_gstin", ""))
                    & ~models.Q(("invoice_number", ""))
                ),
                fields=("entity", "entityfinid", "doc_type", "seller_gstin", "invoice_number"),
                name="uq_sales_hdr_gstin_doc_invno",
            ),
        ),
    ]
