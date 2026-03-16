from __future__ import annotations

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.serializers.statutory.gstr1_serializers import (
    Gstr1RowSerializer,
    Gstr1SectionSummarySerializer,
    Gstr1TotalsSerializer,
)
from reports.services.statutory.gstr1_service import Gstr1Service


class Gstr1Pagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class Gstr1ReportAPIView(APIView):
    """GSTR-1 register endpoint with section summary and paginated rows."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = Gstr1Pagination
    service_class = Gstr1Service

    def get(self, request):
        service = self.service_class()
        queryset = service.get_base_queryset()
        queryset, cleaned_filters = service.apply_filters(queryset, request.query_params)
        queryset = service.annotate_register_fields(queryset).order_by(
            "bill_date",
            "posting_date",
            "doc_code",
            "doc_no",
            "id",
        )

        totals = service.calculate_totals(queryset)
        section_summary = service.summarize_by_section(queryset)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = []
        for row in page:
            row.drilldown = service.build_drilldown(row)
            row.grand_total = row.signed_grand_total
            rows.append(row)

        payload = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": Gstr1RowSerializer(rows, many=True).data,
            "totals": Gstr1TotalsSerializer(totals).data,
            "section_summary": Gstr1SectionSummarySerializer(section_summary, many=True).data,
        }
        return Response(
            build_report_envelope(
                report_code="gstr1-register",
                report_name="GSTR-1 Register",
                payload=payload,
                filters={
                    "from_date": cleaned_filters.get("from_date"),
                    "to_date": cleaned_filters.get("to_date"),
                    "entity": cleaned_filters.get("entity"),
                    "entityfinid": cleaned_filters.get("entityfinid"),
                    "subentity": cleaned_filters.get("subentity"),
                    "customer": cleaned_filters.get("customer"),
                    "customer_gstin": cleaned_filters.get("customer_gstin"),
                    "doc_type": request.query_params.get("doc_type"),
                    "status": request.query_params.get("status"),
                    "supply_category": request.query_params.get("supply_category"),
                    "taxability": request.query_params.get("taxability"),
                    "tax_regime": request.query_params.get("tax_regime"),
                    "is_b2b": cleaned_filters.get("is_b2b"),
                    "is_b2c": cleaned_filters.get("is_b2c"),
                    "is_export": cleaned_filters.get("is_export"),
                    "is_sez": cleaned_filters.get("is_sez"),
                    "is_deemed_export": cleaned_filters.get("is_deemed_export"),
                    "search": cleaned_filters.get("search"),
                    "page": paginator.page.number,
                    "page_size": paginator.get_page_size(request),
                },
                defaults={
                    "decimal_places": 2,
                    "show_zero_balances_default": True,
                    "show_opening_balance_default": False,
                    "enable_drilldown": True,
                },
            )
        )
