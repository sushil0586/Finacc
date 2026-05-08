from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.serializers.summary import Gstr9SummarySerializer
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.views.utils import Gstr9ScopedReportMixin, filtered_query, parse_freeze_version, scope_filters
from reports.schemas.common import build_report_envelope


class Gstr9SummaryAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def get(self, request):
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
            payload = frozen.get("payload", {}).get("summary") or service.summary(scope)
            frozen_meta = {
                "version": frozen["version"],
                "frozen_at": frozen["frozen_at"],
                "frozen_by": frozen["frozen_by"],
            }
        else:
            payload = service.summary(scope)
        response_payload = {
            "summary": Gstr9SummarySerializer(payload).data,
        }
        if frozen_meta:
            response_payload["freeze"] = frozen_meta
        response = build_report_envelope(
            report_code="gstr9-summary",
            report_name="GSTR-9 Summary",
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
            "excel": f"/api/reports/gstr9/export/?format=xlsx&{query}",
            "csv": f"/api/reports/gstr9/export/?format=csv&{query}",
            "json": f"/api/reports/gstr9/export/?format=json&{query}",
        }
        response["available_exports"] = ["excel", "csv", "json"]
        return Response(response)
