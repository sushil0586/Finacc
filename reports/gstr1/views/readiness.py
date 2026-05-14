from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.serializers.summary import Gstr1SummarySerializer
from reports.gstr1.serializers.validation import Gstr1ReadinessSerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import Gstr1ScopedReportMixin, attach_gstr1_export_actions, scope_filters


class Gstr1ReadinessAPIView(Gstr1ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        self.enforce_report_scope(request, scope)
        smart_filters = service.build_smart_filters(request.query_params)
        summary = service.summary(scope, smart_filters=smart_filters)
        payload = service.readiness(scope, smart_filters=smart_filters, summary=summary)
        response_payload = {
            "readiness": Gstr1ReadinessSerializer(payload).data,
            "summary": Gstr1SummarySerializer(summary).data,
        }
        response = build_report_envelope(
            report_code="gstr1-readiness",
            report_name="GSTR-1 Filing Readiness",
            payload=response_payload,
            filters=scope_filters(scope, smart_filters),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        attach_gstr1_export_actions(response, request)
        return Response(response)
