from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.services.report import Gstr9ReportService


class Gstr9FreezeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def get(self, request):
        service = self.service_class()
        freeze_service = self.freeze_service_class(report_service=service)
        try:
            scope = service.build_scope(request.query_params)
            snapshot = freeze_service.latest(scope)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not snapshot:
            return Response(
                {
                    "detail": "No frozen snapshot found for this scope.",
                    "status": "not_found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(snapshot, status=status.HTTP_200_OK)

    def post(self, request):
        service = self.service_class()
        freeze_service = self.freeze_service_class(report_service=service)
        try:
            scope = service.build_scope(request.data or request.query_params)
            snapshot = freeze_service.freeze(scope, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(snapshot, status=status.HTTP_201_CREATED)


class Gstr9FreezeHistoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService

    def get(self, request):
        service = self.service_class()
        freeze_service = self.freeze_service_class(report_service=service)
        try:
            scope = service.build_scope(request.query_params)
            limit = _parse_limit(request.query_params.get("limit"))
            include_payload = _parse_include_payload(request.query_params.get("include_payload"))
            snapshots = freeze_service.history(scope, limit=limit, include_payload=include_payload)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "report_code": "gstr9",
                "count": len(snapshots),
                "results": snapshots,
            },
            status=status.HTTP_200_OK,
        )


def _parse_limit(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer.") from exc
    if parsed <= 0:
        raise ValueError("limit must be a positive integer.")
    return parsed


def _parse_include_payload(value):
    if value in (None, "", "0", "false", "False", "no", "No"):
        return False
    if value in ("1", "true", "True", "yes", "Yes"):
        return True
    raise ValueError("include_payload must be a boolean.")
