from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.serializers.summary import Gstr1SummarySerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import filtered_query, scope_filters


class Gstr1SummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        payload = service.summary(scope)
        response_payload = {
            "summary": Gstr1SummarySerializer(payload).data,
        }
        response = build_report_envelope(
            report_code="gstr1-summary",
            report_name="GSTR-1 Summary",
            payload=response_payload,
            filters=scope_filters(scope),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        query = filtered_query(request, exclude=["page", "page_size"])
        response["actions"]["export_urls"] = {
            "excel": f"/api/reports/gstr1/export/?format=xlsx&{query}",
            "csv": f"/api/reports/gstr1/export/?format=csv&{query}",
            "json": f"/api/reports/gstr1/export/?format=json&{query}",
        }
        response["available_exports"] = ["excel", "csv", "json"]
        return Response(response)
