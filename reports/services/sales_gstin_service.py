from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, DecimalField, F, Max, Sum, Value
from django.db.models.functions import Coalesce

from reports.services.sales_register_service import SalesRegisterService


ZERO = Decimal("0.00")


class SalesGstinService(SalesRegisterService):
    """GSTIN-wise sales aggregation built on top of sales register rules."""

    def get_grouped_queryset(self, params):
        queryset = self.get_base_queryset()
        queryset, cleaned_filters = self.apply_filters(queryset, params)
        queryset = self.annotate_register_fields(queryset)

        grouped = (
            queryset.values("customer_gstin")
            .annotate(
                customer_name=Coalesce(Max("customer_name"), Value("")),
                invoice_count=Count("id"),
                taxable_amount=Coalesce(Sum("taxable_amount"), ZERO),
                cgst_amount=Coalesce(Sum("cgst_amount"), ZERO),
                sgst_amount=Coalesce(Sum("sgst_amount"), ZERO),
                igst_amount=Coalesce(Sum("igst_amount"), ZERO),
                cess_amount=Coalesce(Sum("cess_amount"), ZERO),
                grand_total=Coalesce(Sum("signed_grand_total"), ZERO),
            )
            .annotate(
                total_tax=F("cgst_amount") + F("sgst_amount") + F("igst_amount") + F("cess_amount"),
            )
            .order_by("customer_gstin")
        )
        return grouped, cleaned_filters

    @staticmethod
    def calculate_summary(grouped_queryset):
        totals = {
            "gstin_count": 0,
            "invoice_count": 0,
            "taxable_amount": ZERO,
            "cgst_amount": ZERO,
            "sgst_amount": ZERO,
            "igst_amount": ZERO,
            "cess_amount": ZERO,
            "grand_total": ZERO,
        }
        seen_gstins = set()
        for row in grouped_queryset:
            gstin = row.get("customer_gstin")
            if gstin not in seen_gstins:
                seen_gstins.add(gstin)
                totals["gstin_count"] += 1
            totals["invoice_count"] += int(row.get("invoice_count") or 0)
            totals["taxable_amount"] += Decimal(str(row.get("taxable_amount") or ZERO))
            totals["cgst_amount"] += Decimal(str(row.get("cgst_amount") or ZERO))
            totals["sgst_amount"] += Decimal(str(row.get("sgst_amount") or ZERO))
            totals["igst_amount"] += Decimal(str(row.get("igst_amount") or ZERO))
            totals["cess_amount"] += Decimal(str(row.get("cess_amount") or ZERO))
            totals["grand_total"] += Decimal(str(row.get("grand_total") or ZERO))
        totals["total_tax"] = totals["cgst_amount"] + totals["sgst_amount"] + totals["igst_amount"] + totals["cess_amount"]
        return totals
