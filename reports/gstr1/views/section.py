from __future__ import annotations

from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.serializers.section import Gstr1SectionEnvelopeSerializer, Gstr1SectionRowSerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.services.section import Gstr1SectionService
from reports.gstr1.views.utils import filtered_query, scope_filters


class Gstr1SectionPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500
    page_query_param = "page"


class Gstr1SectionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = Gstr1SectionPagination
    service_class = Gstr1ReportService

    def get(self, request, section_name):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        smart_filters = service.build_smart_filters(request.query_params)
        qs = service.section(scope, section_name, smart_filters=smart_filters)
        qs = Gstr1SectionService.annotate_rows(qs).order_by(
            "bill_date",
            "doc_code",
            "doc_no",
            "id",
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = []
        for row in page:
            row.drilldown = Gstr1SectionService.build_drilldown(row)
            row.taxable_amount = row.signed_taxable_amount
            row.cgst_amount = row.signed_cgst_amount
            row.sgst_amount = row.signed_sgst_amount
            row.igst_amount = row.signed_igst_amount
            row.cess_amount = row.signed_cess_amount
            row.grand_total = row.signed_grand_total
            rows.append(row)

        payload = {
            "section": section_name.upper(),
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": Gstr1SectionRowSerializer(rows, many=True).data,
        }
        response_payload = Gstr1SectionEnvelopeSerializer(payload).data
        response = build_report_envelope(
            report_code=f"gstr1-{section_name.lower()}",
            report_name=f"GSTR-1 {section_name.upper()}",
            payload=response_payload,
            filters=scope_filters(scope, smart_filters),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        query = filtered_query(request, exclude=["page", "page_size"], overrides={"section": section_name})
        response["actions"]["export_urls"] = {
            "excel": f"/api/reports/gstr1/export/?format=xlsx&{query}",
            "csv": f"/api/reports/gstr1/export/?format=csv&{query}",
            "json": f"/api/reports/gstr1/export/?format=json&{query}",
        }
        response["available_exports"] = ["excel", "csv", "json"]
        return Response(response)
