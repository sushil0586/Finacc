from __future__ import annotations

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.serializers.sales_register_serializer import (
    SalesRegisterRowSerializer,
    SalesRegisterTotalsSerializer,
)
from reports.services.sales_register_service import SalesRegisterService
from sales.views.rbac import require_sales_scope_permission


class SalesRegisterPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class SalesRegisterAPIView(APIView):
    """Sales register endpoint with full-dataset totals plus paginated rows."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = SalesRegisterPagination
    service_class = SalesRegisterService

    def get(self, request):
        service = self.service_class()
        queryset = service.get_base_queryset()
        queryset, cleaned_filters = service.apply_filters(queryset, request.query_params)
        require_sales_scope_permission(
            user=request.user,
            entity_id=cleaned_filters["entity"],
            permission_codes=("reports.sales_register.view", "reports.sales_register.export"),
            access_mode="operational",
            feature_code="feature_reporting",
            message="Missing permission: reports.sales_register.view",
        )
        queryset = service.annotate_register_fields(queryset).order_by(
            "bill_date",
            "posting_date",
            "doc_code",
            "doc_no",
            "id",
        )
        totals = service.calculate_totals(queryset)

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
            "results": SalesRegisterRowSerializer(rows, many=True).data,
            "totals": SalesRegisterTotalsSerializer(totals).data,
        }
        return Response(
            build_report_envelope(
                report_code="sales-register",
                report_name="Sales Register",
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
                    "enable_drilldown": True,
                },
            )
        )
