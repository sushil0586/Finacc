from __future__ import annotations

import csv
from io import BytesIO, StringIO

from django.http import HttpResponse
from openpyxl import Workbook
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.views.utils import Gstr9ScopedReportMixin, parse_freeze_version


class Gstr9ExportAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if "format" in request.query_params:
            request._gstr9_export_format = request.query_params.get("format")
            mutable = request._request.GET.copy()
            mutable.pop("format", None)
            request._request.GET = mutable
        return request

    def get(self, request):
        export_format = (getattr(request, "_gstr9_export_format", None) or request.query_params.get("format") or "json").lower()
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        self.enforce_report_scope(request, scope)
        freeze_service = self.freeze_service_class(report_service=service)
        try:
            freeze_version = parse_freeze_version(request.query_params)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        if "freeze_version" in request.query_params:
            frozen = freeze_service.get_snapshot(scope, version=freeze_version)
            if not frozen:
                requested = request.query_params.get("freeze_version") or "latest"
                return Response({"detail": f"Frozen snapshot not found for freeze_version={requested}."}, status=404)
            payload = {
                "summary": frozen.get("payload", {}).get("summary") or service.summary(scope),
                "validations": frozen.get("payload", {}).get("validations") or [],
                "freeze": {
                    "version": frozen["version"],
                    "frozen_at": frozen["frozen_at"],
                    "frozen_by": frozen["frozen_by"],
                },
            }
        else:
            payload = service.export_payload(scope)

        if export_format == "json":
            return Response(payload)
        if export_format == "csv":
            content = self._export_csv(payload)
            return _file_response("GSTR9_Summary.csv", content, "text/csv")
        if export_format == "xlsx":
            content = self._export_xlsx(payload)
            return _file_response(
                "GSTR9_Summary.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)

    def _export_csv(self, payload: dict) -> bytes:
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(["section", "value"])
        summary = payload.get("summary") or {}
        writer.writerow(["phase", summary.get("phase")])
        writer.writerow(["status", summary.get("status")])
        writer.writerow(["message", summary.get("message")])
        for row in summary.get("tables") or []:
            writer.writerow([row.get("code"), row.get("status")])
        return stream.getvalue().encode("utf-8")

    def _export_xlsx(self, payload: dict) -> bytes:
        workbook = Workbook()
        ws = workbook.active
        ws.title = "GSTR9 Summary"
        ws.append(["section", "value"])
        summary = payload.get("summary") or {}
        ws.append(["phase", summary.get("phase")])
        ws.append(["status", summary.get("status")])
        ws.append(["message", summary.get("message")])
        for row in summary.get("tables") or []:
            ws.append([row.get("code"), row.get("status")])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()


def _file_response(filename: str, content: bytes, content_type: str):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
