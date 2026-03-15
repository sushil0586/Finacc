from __future__ import annotations

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.serializers.purchase_register_serializer import (
    PurchaseRegisterRowSerializer,
    PurchaseRegisterTotalsSerializer,
)
from reports.services.purchase_register_service import PurchaseRegisterService


class PurchaseRegisterPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class PurchaseRegisterAPIView(APIView):
    """Purchase register list endpoint with paginated rows and full-dataset totals."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PurchaseRegisterPagination
    service_class = PurchaseRegisterService

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

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = []
        for row in page:
            row.drilldown = service.build_drilldown(row)
            row.discount_total = row.discount_total_signed
            row.grand_total = row.signed_grand_total
            rows.append(row)

        payload = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": PurchaseRegisterRowSerializer(rows, many=True).data,
            "totals": PurchaseRegisterTotalsSerializer(totals).data,
        }
        return Response(
            build_report_envelope(
                report_code="purchase-register",
                report_name="Purchase Register",
                payload=payload,
                filters={
                    "from_date": cleaned_filters.get("from_date"),
                    "to_date": cleaned_filters.get("to_date"),
                    "posting_from_date": cleaned_filters.get("posting_from_date"),
                    "posting_to_date": cleaned_filters.get("posting_to_date"),
                    "entity": cleaned_filters.get("entity"),
                    "entityfinid": cleaned_filters.get("entityfinid"),
                    "subentity": cleaned_filters.get("subentity"),
                    "vendor": cleaned_filters.get("vendor"),
                    "supplier_gstin": cleaned_filters.get("supplier_gstin"),
                    "doc_type": request.query_params.get("doc_type"),
                    "status": request.query_params.get("status"),
                    "reverse_charge": cleaned_filters.get("reverse_charge"),
                    "itc_eligibility": cleaned_filters.get("itc_eligibility"),
                    "itc_claim_status": request.query_params.get("itc_claim_status"),
                    "blocked_itc": cleaned_filters.get("blocked_itc"),
                    "gstr2b_match_status": request.query_params.get("gstr2b_match_status"),
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
