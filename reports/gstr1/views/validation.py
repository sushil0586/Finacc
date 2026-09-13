from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.serializers.validation import Gstr1ReadinessSerializer, Gstr1ValidationWarningSerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import Gstr1ScopedReportMixin, attach_gstr1_export_actions, scope_filters


class Gstr1ValidationAPIView(Gstr1ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        permission_codes = self.enforce_report_scope(request, scope)
        smart_filters = service.build_smart_filters(request.query_params)
        summary = service.summary(scope, smart_filters=smart_filters)
        readiness = service.readiness(scope, smart_filters=smart_filters, summary=summary)
        warnings = readiness["warnings"]
        severity = getattr(smart_filters, "warning_severity", None)
        if severity:
            warnings = [warning for warning in warnings if str(warning.get("severity", "")).lower() == severity]
        payload = {
            "warnings": Gstr1ValidationWarningSerializer(warnings, many=True).data,
            "warning_count": len(warnings),
            "readiness": Gstr1ReadinessSerializer(readiness).data,
        }
        response = build_report_envelope(
            report_code="gstr1-validations",
            report_name="GSTR-1 Validations",
            payload=payload,
            filters=scope_filters(scope, smart_filters),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        attach_gstr1_export_actions(response, request, permission_codes=permission_codes)
        return Response(response)
