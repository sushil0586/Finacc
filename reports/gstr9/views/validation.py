from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.serializers.validation import Gstr9ValidationWarningSerializer
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.views.utils import parse_freeze_version, scope_filters
from reports.schemas.common import build_report_envelope


class Gstr9ValidationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
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
            warnings = frozen.get("payload", {}).get("validations") or []
            frozen_meta = {
                "version": frozen["version"],
                "frozen_at": frozen["frozen_at"],
                "frozen_by": frozen["frozen_by"],
            }
        else:
            warnings = service.validations(scope)
        payload = {
            "warnings": Gstr9ValidationWarningSerializer(warnings, many=True).data,
            "warning_count": len(warnings),
        }
        if frozen_meta:
            payload["freeze"] = frozen_meta
        response = build_report_envelope(
            report_code="gstr9-validations",
            report_name="GSTR-9 Validations",
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
