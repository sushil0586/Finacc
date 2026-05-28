from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.report_permissions import assert_any_report_permission
from reports.gstr3b.exporters import export_gstr3b_csv_rows, export_gstr3b_excel
from reports.gstr3b.selectors import scope_filters
from reports.gstr3b.serializers import Gstr3bSummarySerializer, Gstr3bValidationSerializer
from reports.gstr3b.services import Gstr3bSummaryService
from reports.schemas.common import build_report_envelope
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class Gstr3bSummaryAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr3bSummaryService
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def enforce_report_permission(self, request, *, entity_id: int):
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=("reports.gstr3b.view",),
            message="You do not have permission to access the GSTR-3B workspace.",
        )

    def get(self, request):
        service = self.service_class()
        try:
            scope = service.build_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)
        self.enforce_scope(request, entity_id=scope.entity_id, entityfinid_id=scope.entityfinid_id, subentity_id=scope.subentity_id)
        self.enforce_report_permission(request, entity_id=scope.entity_id)

        payload = {
            "summary": Gstr3bSummarySerializer(service.build(scope)).data,
        }
        response = build_report_envelope(
            report_code="gstr3b-summary",
            report_name="GSTR-3B Summary",
            payload=payload,
            filters=scope_filters(scope),
            defaults={
                "decimal_places": 2,
                "show_zero_balances_default": True,
                "show_opening_balance_default": False,
                "enable_drilldown": True,
            },
        )
        response["available_exports"] = ["json", "xlsx", "csv"]
        response["actions"]["can_export_excel"] = True
        response["actions"]["can_export_pdf"] = False
        response["actions"]["can_export_csv"] = True
        return Response(response)


class Gstr3bMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        entity_id = int(entity_id)
        self.enforce_scope(request, entity_id=entity_id)
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=("reports.gstr3b.view",),
            message="You do not have permission to access the GSTR-3B workspace.",
        )
        return Response(
            {
                "report_code": "gstr3b-summary",
                "report_name": "GSTR-3B Summary",
                "supported_sections": ["3.1", "3.2", "4", "5.1", "6.1"],
                "supported_exports": ["json", "xlsx", "csv"],
                "phase": 2,
            }
        )


class Gstr3bValidationAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr3bSummaryService
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        service = self.service_class()
        try:
            scope = service.build_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)
        self.enforce_scope(request, entity_id=scope.entity_id, entityfinid_id=scope.entityfinid_id, subentity_id=scope.subentity_id)
        assert_any_report_permission(
            user=request.user,
            entity_id=scope.entity_id,
            required_permissions=("reports.gstr3b.view",),
            message="You do not have permission to access the GSTR-3B workspace.",
        )
        warnings = Gstr3bValidationSerializer(service.validations(scope), many=True).data
        return Response({"warnings": warnings})


class Gstr3bExportAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    service_class = Gstr3bSummaryService
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if "format" in request.query_params:
            request._gstr3b_export_format = request.query_params.get("format")
            mutable = request._request.GET.copy()
            mutable.pop("format", None)
            request._request.GET = mutable
        return request

    def get(self, request):
        export_format = (getattr(request, "_gstr3b_export_format", None) or request.query_params.get("format") or "json").lower()
        service = self.service_class()
        try:
            scope = service.build_scope(request.query_params)
        except ValidationError as exc:
            return Response(exc.message_dict, status=400)
        self.enforce_scope(request, entity_id=scope.entity_id, entityfinid_id=scope.entityfinid_id, subentity_id=scope.subentity_id)
        assert_any_report_permission(
            user=request.user,
            entity_id=scope.entity_id,
            required_permissions=("reports.gstr3b.view",),
            message="You do not have permission to access the GSTR-3B workspace.",
        )

        summary = Gstr3bSummarySerializer(service.build(scope)).data
        warnings = Gstr3bValidationSerializer(service.validations(scope), many=True).data
        if export_format == "json":
            return Response({"summary": summary, "warnings": warnings})
        if export_format == "csv":
            content = export_gstr3b_csv_rows(summary=summary, warnings=warnings)
            return _file_response("GSTR3B_Summary.csv", content, "text/csv")
        if export_format == "xlsx":
            content = export_gstr3b_excel(
                summary=summary,
                warnings=warnings,
                audit_context={
                    "generated_on": timezone.now().isoformat(),
                    "scope": _format_audit_scope(scope),
                },
            )
            return _file_response(
                "GSTR3B_Summary.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return Response({"detail": "Unsupported export format."}, status=400)


def _file_response(filename, content, content_type):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _format_audit_scope(scope) -> str:
    parts = [
        f"entity={scope.entity_id}",
        f"entityfinid={scope.entityfinid_id}",
        f"subentity={scope.subentity_id or '-'}",
        f"from_date={scope.from_date.isoformat()}",
        f"to_date={scope.to_date.isoformat()}",
    ]
    return ", ".join(parts)
