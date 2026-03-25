from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Max, Min, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary

from reports.gstr1.services.classification import Gstr1ClassificationService, SECTION_B2B, SECTION_B2CL, SECTION_B2CS, SECTION_CDNR, SECTION_CDNUR, SECTION_EXP

ZERO = Decimal("0.00")


class Gstr1SummaryService:
    def __init__(self, *, base_queryset):
        self.base_queryset = base_queryset

    def build_section_totals(self):
        totals = {}
        for section in Gstr1ClassificationService.section_codes():
            totals[section] = self._section_totals(section)
        return totals

    def _section_totals(self, section_code: str):
        qs = self.base_queryset.filter(Gstr1ClassificationService.section_filter(section_code))
        qs = self._annotate_signed_amounts(qs)
        agg = qs.aggregate(
            document_count=Count("id"),
            taxable_amount=Coalesce(Sum("signed_taxable"), ZERO),
            cgst_amount=Coalesce(Sum("signed_cgst"), ZERO),
            sgst_amount=Coalesce(Sum("signed_sgst"), ZERO),
            igst_amount=Coalesce(Sum("signed_igst"), ZERO),
            cess_amount=Coalesce(Sum("signed_cess"), ZERO),
            grand_total=Coalesce(Sum("signed_grand_total"), ZERO),
        )
        agg["section"] = section_code
        return agg

    def hsn_summary(self):
        sign = Case(
            When(header__status=SalesInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(header__doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )

        # Amount/tax part comes from tax summary so both product lines and charge lines are included.
        tax_rows = list(
            SalesTaxSummary.objects.filter(header__in=self.base_queryset)
            .annotate(
                signed_taxable=F("taxable_value") * sign,
                signed_cgst=F("cgst_amount") * sign,
                signed_sgst=F("sgst_amount") * sign,
                signed_igst=F("igst_amount") * sign,
                signed_cess=F("cess_amount") * sign,
            )
            .values("hsn_sac_code", "is_service", "gst_rate")
            .annotate(
                taxable_value=Coalesce(Sum("signed_taxable"), ZERO),
                cgst_amount=Coalesce(Sum("signed_cgst"), ZERO),
                sgst_amount=Coalesce(Sum("signed_sgst"), ZERO),
                igst_amount=Coalesce(Sum("signed_igst"), ZERO),
                cess_amount=Coalesce(Sum("signed_cess"), ZERO),
                document_count=Count("header_id", distinct=True),
            )
            .order_by("hsn_sac_code", "gst_rate", "is_service")
        )

        # Quantity exists only on material/service lines (not on header charges).
        qty_map = {}
        qty_rows = (
            SalesInvoiceLine.objects.filter(header__in=self.base_queryset)
            .annotate(signed_qty=F("qty") * sign)
            .values("hsn_sac_code", "is_service", "gst_rate")
            .annotate(total_qty=Coalesce(Sum("signed_qty"), ZERO))
        )
        for row in qty_rows:
            key = (row.get("hsn_sac_code") or "", bool(row.get("is_service")), row.get("gst_rate"))
            qty_map[key] = row.get("total_qty") or ZERO

        for row in tax_rows:
            key = (row.get("hsn_sac_code") or "", bool(row.get("is_service")), row.get("gst_rate"))
            row["total_qty"] = qty_map.get(key, ZERO)

        return tax_rows

    def nil_exempt_summary(self):
        qs = SalesTaxSummary.objects.filter(
            header__in=self.base_queryset,
            taxability__in=[
                SalesInvoiceHeader.Taxability.EXEMPT,
                SalesInvoiceHeader.Taxability.NIL_RATED,
                SalesInvoiceHeader.Taxability.NON_GST,
            ],
        )
        return list(
            qs.values("taxability")
            .annotate(
                taxable_value=Coalesce(Sum("taxable_value"), ZERO),
                cgst_amount=Coalesce(Sum("cgst_amount"), ZERO),
                sgst_amount=Coalesce(Sum("sgst_amount"), ZERO),
                igst_amount=Coalesce(Sum("igst_amount"), ZERO),
                cess_amount=Coalesce(Sum("cess_amount"), ZERO),
            )
            .order_by("taxability")
        )

    def document_summary(self):
        qs = self.base_queryset
        return list(
            qs.values("doc_type", "doc_code")
            .annotate(
                document_count=Count("id"),
                cancelled_count=Count("id", filter=Q(status=SalesInvoiceHeader.Status.CANCELLED)),
                min_doc_no=Min("doc_no"),
                max_doc_no=Max("doc_no"),
            )
            .order_by("doc_type", "doc_code")
        )

    def _annotate_signed_amounts(self, qs):
        sign = Case(
            When(status=SalesInvoiceHeader.Status.CANCELLED, then=Value(Decimal("0"))),
            When(doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE, then=Value(Decimal("-1"))),
            default=Value(Decimal("1")),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        return qs.annotate(
            signed_taxable=F("total_taxable_value") * sign,
            signed_cgst=F("total_cgst") * sign,
            signed_sgst=F("total_sgst") * sign,
            signed_igst=F("total_igst") * sign,
            signed_cess=F("total_cess") * sign,
            signed_grand_total=F("grand_total") * sign,
        )


SECTION_LABELS = {
    SECTION_B2B.code: SECTION_B2B.label,
    SECTION_B2CL.code: SECTION_B2CL.label,
    SECTION_B2CS.code: SECTION_B2CS.label,
    SECTION_CDNR.code: SECTION_CDNR.label,
    SECTION_CDNUR.code: SECTION_CDNUR.label,
    SECTION_EXP.code: SECTION_EXP.label,
}
