from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, CharField, DecimalField, F, Value, When

from sales.models import SalesInvoiceHeader


class Gstr1SectionService:
    @staticmethod
    def annotate_rows(qs):
        sign = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        return qs.annotate(
            invoice_date=F("bill_date"),
            doc_type_name=Case(
                *[
                    When(doc_type=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.DocType
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            status_name=Case(
                *[
                    When(status=choice.value, then=Value(str(choice.label)))
                    for choice in SalesInvoiceHeader.Status
                ],
                default=Value(""),
                output_field=CharField(),
            ),
            signed_taxable_amount=F("total_taxable_value") * sign,
            signed_cgst_amount=F("total_cgst") * sign,
            signed_sgst_amount=F("total_sgst") * sign,
            signed_igst_amount=F("total_igst") * sign,
            signed_cess_amount=F("total_cess") * sign,
            signed_grand_total=F("grand_total") * sign,
        )

    @staticmethod
    def build_drilldown(row):
        return {
            "target": "sales_invoice_detail",
            "id": row.id,
            "doc_type": row.doc_type,
            "invoice_number": row.invoice_number,
        }
