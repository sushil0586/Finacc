from __future__ import annotations

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.serializers.sales_gstin_serializer import (
    SalesGstinRowSerializer,
    SalesGstinSummarySerializer,
)
from reports.services.sales_gstin_service import SalesGstinService


class SalesGstinPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class SalesGstinAPIView(APIView):
    """Sales GSTIN-wise report endpoint."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = SalesGstinPagination
    service_class = SalesGstinService

    def get(self, request):
        service = self.service_class()
        grouped_queryset, cleaned_filters = service.get_grouped_queryset(request.query_params)
        summary = service.calculate_summary(grouped_queryset)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(grouped_queryset, request, view=self)

        payload = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": SalesGstinRowSerializer(page, many=True).data,
            "summary": SalesGstinSummarySerializer(summary).data,
        }

        return Response(
            build_report_envelope(
                report_code="sales-gstin",
                report_name="Sales GSTIN Report",
                payload=payload,
                filters={
                    "from_date": cleaned_filters.get("from_date"),
                    "to_date": cleaned_filters.get("to_date"),
                    "posting_from_date": cleaned_filters.get("posting_from_date"),
                    "posting_to_date": cleaned_filters.get("posting_to_date"),
                    "entity": cleaned_filters.get("entity"),
                    "entityfinid": cleaned_filters.get("entityfinid"),
                    "subentity": cleaned_filters.get("subentity"),
                    "customer": cleaned_filters.get("customer"),
                    "customer_gstin": cleaned_filters.get("customer_gstin"),
                    "doc_type": request.query_params.get("doc_type"),
                    "status": request.query_params.get("status"),
                    "invoice_type": request.query_params.get("invoice_type"),
                    "supply_classification": request.query_params.get("supply_classification"),
                    "is_b2b": cleaned_filters.get("is_b2b"),
                    "is_b2c": cleaned_filters.get("is_b2c"),
                    "is_export": cleaned_filters.get("is_export"),
                    "is_sez": cleaned_filters.get("is_sez"),
                    "is_deemed_export": cleaned_filters.get("is_deemed_export"),
                    "min_amount": cleaned_filters.get("min_amount"),
                    "max_amount": cleaned_filters.get("max_amount"),
                    "search": cleaned_filters.get("search"),
                    "page": paginator.page.number,
                    "page_size": paginator.get_page_size(request),
                },
                defaults={
                    "decimal_places": 2,
                    "show_zero_balances_default": True,
                    "show_opening_balance_default": False,
                    "enable_drilldown": False,
                },
            )
        )
