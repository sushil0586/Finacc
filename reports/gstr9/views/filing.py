from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr9.services.filing import Gstr9FilingService
from reports.gstr9.services.freeze import Gstr9FreezeService
from reports.gstr9.services.report import Gstr9ReportService
from reports.gstr9.views.utils import Gstr9ScopedReportMixin


class Gstr9FilingPrepareAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService
    filing_service_class = Gstr9FilingService

    def post(self, request):
        service = self.service_class()
        scope = service.build_scope(request.data or request.query_params)
        self.enforce_report_scope(request, scope)
        freeze_service = self.freeze_service_class(report_service=service)
        filing_service = self.filing_service_class(freeze_service=freeze_service)
        try:
            freeze_version = _parse_required_positive_int(request.data.get("freeze_version"), "freeze_version")
            payload = filing_service.prepare(scope, freeze_version=freeze_version, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload, status=status.HTTP_201_CREATED)


class Gstr9FilingSubmitAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService
    filing_service_class = Gstr9FilingService

    def post(self, request):
        service = self.service_class()
        scope = service.build_scope(request.data or request.query_params)
        self.enforce_report_scope(request, scope)
        freeze_service = self.freeze_service_class(report_service=service)
        filing_service = self.filing_service_class(freeze_service=freeze_service)
        try:
            filing_id = _parse_required_positive_int(request.data.get("filing_id"), "filing_id")
            payload = filing_service.submit(scope, filing_id=filing_id, user=request.user, submission_data=dict(request.data or {}))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload, status=status.HTTP_200_OK)


class Gstr9FilingStatusAPIView(Gstr9ScopedReportMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr9ReportService
    freeze_service_class = Gstr9FreezeService
    filing_service_class = Gstr9FilingService

    def get(self, request):
        service = self.service_class()
        scope = service.build_scope(request.query_params)
        self.enforce_report_scope(request, scope)
        freeze_service = self.freeze_service_class(report_service=service)
        filing_service = self.filing_service_class(freeze_service=freeze_service)
        try:
            filing_id = _parse_optional_positive_int(request.query_params.get("filing_id"), "filing_id")
            limit = _parse_optional_positive_int(request.query_params.get("limit"), "limit") or 10
            payload = filing_service.status(scope, filing_id=filing_id, limit=limit)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if filing_id is not None:
            if not payload:
                return Response({"detail": f"Filing run not found for filing_id={filing_id}."}, status=status.HTTP_404_NOT_FOUND)
            return Response(payload, status=status.HTTP_200_OK)
        return Response({"report_code": "gstr9", "count": len(payload), "results": payload}, status=status.HTTP_200_OK)


def _parse_required_positive_int(value, field):
    if value in (None, ""):
        raise ValueError(f"{field} is required.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return parsed


def _parse_optional_positive_int(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return parsed
