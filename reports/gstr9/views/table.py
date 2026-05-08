from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.serializers.table import Gstr9TableEnvelopeSerializer
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.views.utils import Gstr9ScopedReportMixin, parse_freeze_version, scope_filters
from reports.schemas.common import build_report_envelope


class Gstr9TableAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def get(self, request, table_code: str):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        self.enforce_report_scope(request, scope)
        freeze_service = self.freeze_service_class(report_service=service)
        frozen_meta = None
        try:
            freeze_version = parse_freeze_version(request.query_params)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        if "freeze_version" in request.query_params:
            frozen = freeze_service.get_snapshot(scope, version=freeze_version)
            if not frozen:
                requested = request.query_params.get("freeze_version") or "latest"
                return Response({"detail": f"Frozen snapshot not found for freeze_version={requested}."}, status=404)
            payload = (frozen.get("payload", {}).get("tables") or {}).get(str(table_code or "").strip().upper())
            if not payload:
                return Response({"detail": f"Table {table_code} not found in frozen snapshot."}, status=404)
            frozen_meta = {
                "version": frozen["version"],
                "frozen_at": frozen["frozen_at"],
                "frozen_by": frozen["frozen_by"],
            }
        else:
            payload = service.table(scope, table_code)
        response = build_report_envelope(
            report_code=f"gstr9-table-{table_code.lower()}",
            report_name=f"GSTR-9 {payload['table_label']}",
            payload=Gstr9TableEnvelopeSerializer(payload).data,
            filters=scope_filters(scope),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": False,
            },
        )
        if frozen_meta:
            response["freeze"] = frozen_meta
        return Response(response)
