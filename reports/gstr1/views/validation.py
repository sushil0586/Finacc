from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.gstr1.serializers.validation import Gstr1ValidationWarningSerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.views.utils import scope_filters


class Gstr1ValidationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        warnings = service.validations(scope)
        payload = {
            "warnings": Gstr1ValidationWarningSerializer(warnings, many=True).data,
            "warning_count": len(warnings),
        }
        response = build_report_envelope(
            report_code="gstr1-validations",
            report_name="GSTR-1 Validations",
            payload=payload,
            filters=scope_filters(scope),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        return Response(response)
