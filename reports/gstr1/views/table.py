from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr1.serializers.table import Gstr1TableEnvelopeSerializer
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr1.services.table_views import Gstr1TableViewService
from reports.gstr1.views.utils import scope_filters
from reports.schemas.common import build_report_envelope


class Gstr1TableAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr1ReportService

    def get(self, request, table_code: str):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        smart_filters = service.build_smart_filters(request.query_params)
        qs = service.scoped_queryset(scope)
        table_service = Gstr1TableViewService(scope=scope, base_queryset=qs)
        payload = table_service.build(table_code)
        response = build_report_envelope(
            report_code=f"gstr1-table-{table_code.lower()}",
            report_name=f"GSTR-1 {payload['table_label']}",
            payload=Gstr1TableEnvelopeSerializer(payload).data,
            filters=scope_filters(scope, smart_filters),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": False,
            },
        )
        return Response(response)
